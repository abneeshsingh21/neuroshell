// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// Native unit tests for the NeuroShell C++ host (no framework dependency).
// Build & run:  cmake -B build && cmake --build build && ctest --test-dir build
#include <cassert>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "version.hpp"
#include "safe_exec.hpp"
#include "shm_ipc.hpp"
#include "dlp_masker.hpp"
#include "crypto/sha2.hpp"
#include "crypto/ed25519.hpp"
#include "json_mini.hpp"
#include "update_verifier.hpp"
#include "stream_reader.hpp"
#include "history_engine.hpp"
#include "blast_radius.hpp"
#include "undo_engine.hpp"
#include "sandbox_engine.hpp"

#include <thread>
#if defined(__linux__)
#include <sys/wait.h>
#endif

static int g_failures = 0;
static int g_checks = 0;

#define CHECK(cond)                                                          \
    do {                                                                     \
        ++g_checks;                                                          \
        if (!(cond)) {                                                       \
            ++g_failures;                                                    \
            std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);      \
        }                                                                    \
    } while (0)

// ─── Semver comparison (regression: lexicographic "10.0.0" < "5.7.0") ───
static void TestSemver() {
    using neuroshell::version::CompareSemver;
    using neuroshell::version::IsNewerRelease;

    CHECK(CompareSemver("5.8.0", "5.8.0") == 0);
    CHECK(CompareSemver("5.8.1", "5.8.0") > 0);
    CHECK(CompareSemver("5.7.9", "5.8.0") < 0);
    CHECK(CompareSemver("10.0.0", "9.9.9") > 0);      // numeric, not lexicographic
    CHECK(CompareSemver("v6.0.0", "5.8.0") > 0);      // leading 'v'
    CHECK(CompareSemver("6.0.0-rc.1", "6.0.0") == 0); // pre-release stripped
    CHECK(CompareSemver("garbage", "5.8.0") < 0);     // non-numeric -> 0.0.0

    CHECK(!IsNewerRelease(NEUROSHELL_VERSION));
    CHECK(IsNewerRelease("99.0.0"));
    CHECK(!IsNewerRelease("0.0.1"));
}

// ─── safe_exec validators (injection surface) ───
static void TestValidators() {
    using namespace neuroshell::safe_exec;

    CHECK(IsValidRepoSlug("vercel/next.js"));
    CHECK(IsValidRepoSlug("abneeshsingh21/neuroshell"));
    CHECK(!IsValidRepoSlug("owner/repo; rm -rf /"));
    CHECK(!IsValidRepoSlug("owner/repo && curl evil"));
    CHECK(!IsValidRepoSlug("$(whoami)/x"));
    CHECK(!IsValidRepoSlug("a/b/c"));
    CHECK(!IsValidRepoSlug("../../etc/passwd"));
    CHECK(!IsValidRepoSlug(""));
    CHECK(!IsValidRepoSlug("/leading"));
    CHECK(!IsValidRepoSlug("trailing/"));

    CHECK(IsValidGitHubUser("torvalds"));
    CHECK(IsValidGitHubUser("my-org-42"));
    CHECK(!IsValidGitHubUser("user`id`"));
    CHECK(!IsValidGitHubUser("-leading"));
    CHECK(!IsValidGitHubUser("a b"));

    CHECK(IsValidHost("8.8.8.8"));
    CHECK(IsValidHost("example.com"));
    CHECK(IsValidHost("::1"));
    CHECK(!IsValidHost("evil.com;reboot"));
    CHECK(!IsValidHost("$(cmd)"));

    CHECK(IsValidVaultKey("groq_api_key"));
    CHECK(!IsValidVaultKey("key' -w 'stolen"));
    CHECK(!IsValidVaultKey(""));
}

// ─── Shell quoting ───
static void TestQuoting() {
    using namespace neuroshell::safe_exec;

    CHECK(QuotePosix("simple") == "'simple'");
    CHECK(QuotePosix("with space") == "'with space'");
    // Embedded single quote must be broken out: ' -> '\''
    CHECK(QuotePosix("it's") == "'it'\\''s'");
    // Metacharacters neutralized inside single quotes
    CHECK(QuotePosix("$(rm -rf /)") == "'$(rm -rf /)'");

    CHECK(QuoteWin("simple") == "simple");
    CHECK(QuoteWin("with space") == "\"with space\"");
    CHECK(QuoteWin("say \"hi\"") == "\"say \\\"hi\\\"\"");
}

// ─── SHM ring buffer: ABI layout + roundtrip + wrap ───
static void TestShmLayout() {
    // Compile-time asserts in the header already guarantee the layout; verify
    // runtime constants match the Python bridge expectations.
    CHECK(neuroshell::SHM_HEADER_SIZE == 128);
    CHECK(neuroshell::SHM_ABI_VERSION == 3);
    CHECK(offsetof(neuroshell::SHMHeader, write_cursor) == 64);
    CHECK(offsetof(neuroshell::SHMHeader, read_cursor) == 72);
    CHECK(offsetof(neuroshell::SHMHeader, message_sequence) == 80);
    CHECK(offsetof(neuroshell::SHMHeader, cancel_stream_id) == 84);
}

static void TestShmRoundtrip() {
    neuroshell::SHMRingBuffer host;
    if (!host.initialize_as_host()) {
        std::printf("SKIP shm roundtrip (no /dev/shm access)\n");
        return;
    }

    CHECK(host.write_message("{\"event\":\"hello\"}"));
    CHECK(host.write_message("second"));

    std::string out;
    CHECK(host.read_message(out));
    CHECK(out == "{\"event\":\"hello\"}");
    CHECK(host.read_message(out));
    CHECK(out == "second");
    CHECK(!host.read_message(out)); // empty now

    // Client attach path validates magic/version
    neuroshell::SHMRingBuffer client;
    CHECK(client.attach_as_client());
    CHECK(host.write_message("host->client"));
    CHECK(client.read_message(out));
    CHECK(out == "host->client");
    client.close();

    // Wrap-around stress: push enough messages to cycle the ring twice
    std::string big(300000, 'x');
    for (int i = 0; i < 60; ++i) {
        CHECK(host.write_message(big));
        std::string got;
        CHECK(host.read_message(got));
        CHECK(got.size() == big.size());
        CHECK(got == big);
    }

    // Oversize rejected
    std::string tooBig(neuroshell::SHM_RING_CAPACITY, 'y');
    CHECK(!host.write_message(tooBig));

    host.close();
}

// ─── DLP masker ───
static void TestDlpMasker() {
    neuroshell::DLPMasker masker;

    std::string aws = "creds: AKIAIOSFODNN7EXAMPLE done";
    std::string masked = masker.filter_stream(aws);
    CHECK(masked.find("AKIAIOSFODNN7EXAMPLE") == std::string::npos);

    std::string ghp = "token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    masked = masker.filter_stream(ghp);
    CHECK(masked.find("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") == std::string::npos);

    std::string clean = "just a normal line of build output";
    CHECK(masker.filter_stream(clean) == clean);

    std::string dburi = "postgres://admin:hunter2@db.internal:5432/prod";
    masked = masker.filter_stream(dburi);
    CHECK(masked.find("hunter2") == std::string::npos);
}

// ─── safe_exec argv execution (POSIX only in CI) ───
static void TestRunCapture() {
#if !defined(_WIN32)
    auto res = neuroshell::safe_exec::RunCapture({"echo", "hello world"});
    CHECK(res.spawned);
    CHECK(res.exit_code == 0);
    CHECK(neuroshell::safe_exec::Trim(res.output) == "hello world");

    // Metacharacters are NOT interpreted (no shell involved)
    auto res2 = neuroshell::safe_exec::RunCapture({"echo", "$(id); rm -rf /tmp/x"});
    CHECK(neuroshell::safe_exec::Trim(res2.output) == "$(id); rm -rf /tmp/x");

    // stdin plumbing
    auto res3 = neuroshell::safe_exec::RunCapture({"cat"}, "piped-secret");
    CHECK(neuroshell::safe_exec::Trim(res3.output) == "piped-secret");

    // Nonexistent binary -> 127, not a crash
    auto res4 = neuroshell::safe_exec::RunCapture({"definitely-not-a-real-binary-xyz"});
    CHECK(res4.exit_code == 127);
#endif
}

// ═══════════════════════════════════════════════════════════
// Phase 1: signed self-update pipeline (v5.9)
// ═══════════════════════════════════════════════════════════

// ─── SHA-256 / SHA-512: cross-implementation vectors (Python hashlib) ───
static void TestSha2Vectors() {
    using namespace neuroshell::crypto;

    // NIST/FIPS canonical "abc" vectors
    auto h256 = SHA256::Hash("abc", 3);
    CHECK(ToHex(h256.data(), 32) ==
          "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    auto h512 = SHA512::Hash("abc", 3);
    CHECK(ToHex(h512.data(), 64) ==
          "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
          "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f");

    // Empty message
    auto e256 = SHA256::Hash("", 0);
    CHECK(ToHex(e256.data(), 32) ==
          "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    auto e512 = SHA512::Hash("", 0);
    CHECK(ToHex(e512.data(), 64) ==
          "cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce"
          "47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e");

    // Block-boundary sweep for SHA-512 (128-byte blocks)
    std::string x128(128, 'x');
    auto b512 = SHA512::Hash(x128.data(), x128.size());
    CHECK(ToHex(b512.data(), 64) ==
          "e2e22f8422b54b06e35c3ea30a383d1de7a8fbc27992923074103117020d8dd7"
          "024c3ecf7d6d1a15a6de5a75ff32fb486b9e8ced4c02ffe05822bf2cb734d0e0");

    // 1 MB streamed in odd chunk sizes: exercises the buffering path
    {
        SHA256 h;
        std::string chunk(4099, 'a'); // prime-ish chunk size, not block aligned
        size_t left = 1000000;
        while (left > 0) {
            size_t take = left < chunk.size() ? left : chunk.size();
            h.Update(chunk.data(), take);
            left -= take;
        }
        uint8_t out[32];
        h.Final(out);
        CHECK(ToHex(out, 32) ==
              "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
    }

    // Hex helpers round-trip + constant-time compare
    uint8_t buf[4];
    CHECK(FromHex("deadbeef", buf, 4));
    CHECK(ToHex(buf, 4) == "deadbeef");
    CHECK(!FromHex("deadbee", buf, 4));  // odd length
    CHECK(!FromHex("deadbeeg", buf, 4)); // bad digit
    uint8_t a[3] = {1, 2, 3}, b[3] = {1, 2, 3}, c[3] = {1, 2, 4};
    CHECK(neuroshell::crypto::ConstantTimeEqual(a, b, 3));
    CHECK(!neuroshell::crypto::ConstantTimeEqual(a, c, 3));
}

// ─── Ed25519: RFC 8032 vector + cross-generated vectors + negatives ───
static void TestEd25519() {
    using neuroshell::crypto::Ed25519;
    using neuroshell::crypto::FromHex;

    // RFC 8032 §7.1 TEST 1: empty message, known key
    const std::string rfc_pk = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a";
    const std::string rfc_sig =
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b";
    CHECK(Ed25519::VerifyHex(rfc_sig, nullptr, 0, rfc_pk));

    // Vector cross-generated with Python `cryptography` (OpenSSL Ed25519):
    // seed = 00..1f, msg = "neuroshell-update-manifest-test"
    const std::string pk1 = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8";
    const std::string pk2 = "79b5562e8fe654f94078b112e8a98ba7901f853ae695bed7e0e3910bad049664";
    const std::string msg = "neuroshell-update-manifest-test";
    const std::string sig1 =
        "d350b705c93638569dfb53e01813bfc0154e584607e7e3c28cec8bbb65bec4aae02cc079c8158b42244af2fa2eb03e0834a9fbb37b5de2a2bee3e2e21394d701";
    const uint8_t* mp = reinterpret_cast<const uint8_t*>(msg.data());

    CHECK(Ed25519::VerifyHex(sig1, mp, msg.size(), pk1));

    // Wrong key must fail
    CHECK(!Ed25519::VerifyHex(sig1, mp, msg.size(), pk2));

    // 1-bit tamper of the message must fail
    {
        std::string m2 = msg;
        m2[0] ^= 0x01;
        CHECK(!Ed25519::VerifyHex(sig1, reinterpret_cast<const uint8_t*>(m2.data()), m2.size(), pk1));
    }

    // 1-bit tamper of R and of S must each fail
    {
        uint8_t sig[64], pk[32];
        CHECK(FromHex(sig1, sig, 64));
        CHECK(FromHex(pk1, pk, 32));
        sig[0] ^= 0x01; // R tamper
        CHECK(!Ed25519::Verify(sig, mp, msg.size(), pk));
        sig[0] ^= 0x01;
        sig[40] ^= 0x01; // S tamper
        CHECK(!Ed25519::Verify(sig, mp, msg.size(), pk));
    }

    // RFC 8032 malleability: sig' = (R, S+L) verifies in naive
    // implementations but MUST be rejected here (S >= L non-canonical).
    const std::string mal =
        "d350b705c93638569dfb53e01813bfc0154e584607e7e3c28cec8bbb65bec4aacd00b6d6e2789d9afae6e99d0daa1d1d34a9fbb37b5de2a2bee3e2e21394d711";
    CHECK(!Ed25519::VerifyHex(mal, mp, msg.size(), pk1));

    // Malformed inputs: short/invalid hex, all-zero key (not a curve point)
    CHECK(!Ed25519::VerifyHex("abcd", mp, msg.size(), pk1));
    CHECK(!Ed25519::VerifyHex(sig1, mp, msg.size(), "00"));
    CHECK(!Ed25519::VerifyHex(sig1, mp, msg.size(), std::string(64, '0')));
}

// ─── json_mini: strict parsing of untrusted input ───
static void TestJsonMini() {
    using neuroshell::json::Parser;

    auto v = Parser::Parse(R"({"a": 1, "b": "x", "c": [true, null, -2.5e3], "d": {"e": "\u00e9\ud83d\ude00"}})");
    CHECK(v && v->IsObject());
    int64_t n = 0;
    CHECK(v->GetInt64("a", n) && n == 1);
    CHECK(v->GetString("b") == "x");
    const auto* c = v->Get("c");
    CHECK(c && c->IsArray() && c->arr_v.size() == 3);
    CHECK(c->arr_v[0]->IsBool() && c->arr_v[0]->bool_v);
    CHECK(c->arr_v[1]->IsNull());
    CHECK(c->arr_v[2]->IsNumber() && c->arr_v[2]->num_v == -2500.0);
    const auto* d = v->Get("d");
    CHECK(d && d->GetString("e") == "\xC3\xA9\xF0\x9F\x98\x80"); // é + 😀 as UTF-8

    // Ints with fraction/exponent are rejected by the strict accessor
    auto f = Parser::Parse(R"({"x": 1.5, "y": 1e3})");
    CHECK(f && !f->GetInt64("x", n) && !f->GetInt64("y", n));

    // Syntax violations all fail closed (nullptr, no throw)
    CHECK(!Parser::Parse(""));
    CHECK(!Parser::Parse("{"));
    CHECK(!Parser::Parse("{\"a\":1,}"));           // trailing comma
    CHECK(!Parser::Parse("{'a':1}"));              // single quotes
    CHECK(!Parser::Parse("{\"a\":1} extra"));      // trailing garbage
    CHECK(!Parser::Parse("{\"a\":NaN}"));          // non-standard literal
    CHECK(!Parser::Parse("[01]"));                 // leading zero
    CHECK(!Parser::Parse("\"\\ud800\""));          // lone surrogate
    CHECK(!Parser::Parse(std::string("\"\x01\""))); // raw control char

    // Depth bomb: 100 nested arrays vs cap of 32 — must refuse, not crash
    std::string bomb(100, '[');
    bomb += std::string(100, ']');
    CHECK(!Parser::Parse(bomb));

    // Size cap
    CHECK(!Parser::Parse(std::string(64, ' ') + "1", /*max_bytes=*/8));

    // Duplicate keys: deterministic last-wins
    auto dup = Parser::Parse(R"({"k": "first", "k": "second"})");
    CHECK(dup && dup->GetString("k") == "second");
}

// ─── UpdateVerifier: full policy matrix over a REAL signed manifest ───
static void TestUpdateVerifier() {
    using namespace neuroshell::update;

    // Manifest signed offline with the seed-00..1f test key (Python
    // `cryptography`); signature covers these exact raw bytes.
    const std::string pk1 = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8";
    const std::string manifest =
        "{\"schema\":1,\"version\":\"5.9.0\",\"created_at\":1750000000,\"expires_at\":4102444800,\"min_version\":\"5.0.0\",\"artifacts\":[{\"platform\":\"linux-x86_64\",\"name\":\"neuroshell\",\"sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"size\":1048576,\"url\":\"https://github.com/abneeshsingh21/neuroshell/releases/download/v5.9.0/neuroshell\"},{\"platform\":\"windows-x86_64\",\"name\":\"NeuroShell.exe\",\"sha256\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"size\":2097152,\"url\":\"https://objects.githubusercontent.com/foo/NeuroShell.exe\"}]}";
    const std::string sig =
        "54ad11b1ecb6b81264bac466026affaed80c5101b95e73df0033b1a3e383916299bc626dd7e812dbef638fcae87990e535bc4ca2987a5b5c32cab2cef9e9150f";
    const int64_t now = 1750000100; // just after created_at, well before expiry

    UpdateVerifier ver(pk1, /*running_version=*/"5.8.0");
    VerifiedManifest m;

    // Happy path (linux artifact)
    CHECK(ver.VerifyManifest(manifest, sig, m, now, "linux-x86_64") == VerifyStatus::Ok);
    CHECK(m.version == "5.9.0");
    CHECK(m.artifact.name == "neuroshell");
    CHECK(m.artifact.size == 1048576);

    // Platform routing: windows build picks the .exe artifact
    CHECK(ver.VerifyManifest(manifest, sig, m, now, "windows-x86_64") == VerifyStatus::Ok);
    CHECK(m.artifact.name == "NeuroShell.exe");

    // No artifact for this platform
    CHECK(ver.VerifyManifest(manifest, sig, m, now, "macos-arm64") ==
          VerifyStatus::NoArtifactForPlatform);

    // 1-byte manifest tamper ⇒ BadSignature (raw-bytes signing)
    {
        std::string t = manifest;
        t[t.find("5.9.0") + 2] = '8'; // version 5.9.0 -> 5.8.0 inside signed bytes
        CHECK(ver.VerifyManifest(t, sig, m, now, "linux-x86_64") == VerifyStatus::BadSignature);
    }

    // 1-hex-char signature tamper ⇒ BadSignature
    {
        std::string s2 = sig;
        s2[0] = (s2[0] == 'a') ? 'b' : 'a';
        CHECK(ver.VerifyManifest(manifest, s2, m, now, "linux-x86_64") == VerifyStatus::BadSignature);
    }

    // Replay of an old-but-validly-signed manifest ⇒ Expired
    CHECK(ver.VerifyManifest(manifest, sig, m, /*now=*/4102444801LL, "linux-x86_64") ==
          VerifyStatus::Expired);

    // Downgrade / equal version ⇒ refused (client already at or past 5.9.0)
    {
        UpdateVerifier same(pk1, "5.9.0");
        CHECK(same.VerifyManifest(manifest, sig, m, now, "linux-x86_64") == VerifyStatus::Downgrade);
        UpdateVerifier newer(pk1, "6.0.0");
        CHECK(newer.VerifyManifest(manifest, sig, m, now, "linux-x86_64") == VerifyStatus::Downgrade);
    }

    // Client older than min_version ⇒ BelowMinVersion
    {
        UpdateVerifier ancient(pk1, "4.0.0");
        CHECK(ancient.VerifyManifest(manifest, sig, m, now, "linux-x86_64") ==
              VerifyStatus::BelowMinVersion);
    }

    // Unprovisioned placeholder key ⇒ fail closed BEFORE any parsing
    {
        UpdateVerifier unprov(std::string(64, '0'), "5.8.0");
        CHECK(unprov.VerifyManifest(manifest, sig, m, now, "linux-x86_64") ==
              VerifyStatus::KeyNotProvisioned);
    }

    // Wrong (but well-formed) key ⇒ BadSignature
    {
        UpdateVerifier wrong("79b5562e8fe654f94078b112e8a98ba7901f853ae695bed7e0e3910bad049664",
                             "5.8.0");
        CHECK(wrong.VerifyManifest(manifest, sig, m, now, "linux-x86_64") ==
              VerifyStatus::BadSignature);
    }

    // URL policy unit checks
    CHECK(UpdateVerifier::UrlAllowed(
        "https://github.com/abneeshsingh21/neuroshell/releases/download/v5.9.0/neuroshell"));
    CHECK(UpdateVerifier::UrlAllowed("https://objects.githubusercontent.com/x/y"));
    CHECK(!UpdateVerifier::UrlAllowed("http://github.com/x/y"));             // not https
    CHECK(!UpdateVerifier::UrlAllowed("https://evil.com/github.com/x"));     // wrong host
    CHECK(!UpdateVerifier::UrlAllowed("https://github.com.evil.com/x"));     // suffix trick
    CHECK(!UpdateVerifier::UrlAllowed("https://github.com@evil.com/x"));     // userinfo trick
    CHECK(!UpdateVerifier::UrlAllowed("https://github.com:8443/x"));         // explicit port
    CHECK(!UpdateVerifier::UrlAllowed("https://github.com"));                // no path
    CHECK(!UpdateVerifier::UrlAllowed("https://github.com/a b"));            // whitespace
    CHECK(UpdateVerifier::UrlAllowed("https://GITHUB.COM/x/y"));             // host case-insensitive

    // Digest / filename / semver format validators
    CHECK(UpdateVerifier::ValidSha256Hex(std::string(64, 'a')));
    CHECK(!UpdateVerifier::ValidSha256Hex(std::string(64, 'A'))); // canonical lowercase only
    CHECK(!UpdateVerifier::ValidSha256Hex(std::string(63, 'a')));
    CHECK(UpdateVerifier::SafeFileName("NeuroShell.exe"));
    CHECK(UpdateVerifier::SafeFileName("neuroshell"));
    CHECK(!UpdateVerifier::SafeFileName("../../etc/passwd"));
    CHECK(!UpdateVerifier::SafeFileName("a/b"));
    CHECK(!UpdateVerifier::SafeFileName(".."));
    CHECK(!UpdateVerifier::SafeFileName(""));
    CHECK(UpdateVerifier::LooksLikeSemver("5.9.0"));
    CHECK(!UpdateVerifier::LooksLikeSemver("v5.9.0"));
    CHECK(!UpdateVerifier::LooksLikeSemver("5.9"));
    CHECK(!UpdateVerifier::LooksLikeSemver("5.9.0-rc1"));

    // Artifact file binding: SHA-256 + exact size, tamper ⇒ refused
#if !defined(_WIN32)
    {
        const std::string dir = "/tmp/ns_upd_test";
        std::filesystem::create_directories(dir);
        const std::string path = dir + "/artifact.bin";
        std::string payload(70000, 'Q'); // above kMinArtifactBytes
        {
            std::ofstream f(path, std::ios::binary);
            f.write(payload.data(), static_cast<std::streamsize>(payload.size()));
        }
        auto digest = neuroshell::crypto::SHA256::Hash(payload.data(), payload.size());
        ArtifactInfo art;
        art.sha256 = neuroshell::crypto::ToHex(digest.data(), 32);
        art.size = static_cast<int64_t>(payload.size());
        std::string err;
        CHECK(UpdateVerifier::VerifyArtifactFile(path, art, &err));

        // flip one byte ⇒ refused
        {
            std::fstream f(path, std::ios::in | std::ios::out | std::ios::binary);
            f.seekp(1234);
            f.put('R');
        }
        CHECK(!UpdateVerifier::VerifyArtifactFile(path, art, &err));

        // wrong size ⇒ refused even if we don't touch content
        art.size += 1;
        CHECK(!UpdateVerifier::VerifyArtifactFile(path, art, &err));
        std::filesystem::remove_all(dir);
    }
#endif
}

// ═══════════════════════════════════════════════════════════
// Phase 2: SHM token streaming (ABI v3)
// ═══════════════════════════════════════════════════════════

static void TestStreamFrames() {
    using neuroshell::SHMRingBuffer;
    using neuroshell::StreamFrameType;

    // Use the dedicated stream ring name so this never collides with the
    // event-ring roundtrip test.
    SHMRingBuffer ring(neuroshell::SHM_STREAM_WIN_NAME, neuroshell::SHM_STREAM_POSIX_NAME);
    if (!ring.initialize_as_host()) {
        std::printf("SKIP stream frames (no /dev/shm access)\n");
        return;
    }

    // Frame roundtrip preserves type, id and payload byte-for-byte
    CHECK(ring.write_frame(StreamFrameType::Token, 42, "Hello "));
    CHECK(ring.write_frame(StreamFrameType::Token, 42, "world"));
    CHECK(ring.write_frame(StreamFrameType::End, 42, "{\"cancelled\": false, \"tokens\": 2}"));

    SHMRingBuffer::StreamFrame f;
    CHECK(ring.read_frame(f));
    CHECK(f.type == StreamFrameType::Token);
    CHECK(f.stream_id == 42);
    CHECK(f.payload == "Hello ");
    CHECK(ring.read_frame(f));
    CHECK(f.payload == "world");
    CHECK(ring.read_frame(f));
    CHECK(f.type == StreamFrameType::End);
    CHECK(!ring.read_frame(f)); // empty

    // UTF-8 payloads survive intact (multibyte glyphs split across frames
    // must reassemble byte-exact)
    CHECK(ring.write_frame(StreamFrameType::Token, 7, "caf\xC3"));
    CHECK(ring.write_frame(StreamFrameType::Token, 7, "\xA9 \xF0\x9F\x98\x80"));
    CHECK(ring.read_frame(f));
    std::string reassembled = f.payload;
    CHECK(ring.read_frame(f));
    reassembled += f.payload;
    CHECK(reassembled == "caf\xC3\xA9 \xF0\x9F\x98\x80");

    // Garbage messages (too short / unknown type) are rejected, not surfaced
    CHECK(ring.write_message("abc"));       // 3 bytes < frame header
    CHECK(!ring.read_frame(f));
    CHECK(ring.write_message(std::string("\x09""abcd payload", 13))); // bad type 9
    CHECK(!ring.read_frame(f));

    // Cancellation flag: consumer publishes, producer observes, clear resets
    CHECK(ring.cancel_requested() == 0);
    ring.request_cancel(1234);
    CHECK(ring.cancel_requested() == 1234);
    ring.clear_cancel();
    CHECK(ring.cancel_requested() == 0);

    // drain() discards unread frames
    CHECK(ring.write_frame(StreamFrameType::Token, 9, "stale"));
    ring.drain();
    CHECK(!ring.read_frame(f));
}

static void TestTokenStreamReader() {
    using neuroshell::SHMRingBuffer;
    using neuroshell::StreamFrameType;
    using neuroshell::TokenStreamReader;

    SHMRingBuffer ring(neuroshell::SHM_STREAM_WIN_NAME, neuroshell::SHM_STREAM_POSIX_NAME);
    if (!ring.initialize_as_host()) {
        std::printf("SKIP stream reader (no /dev/shm access)\n");
        return;
    }

    // Stream ids are monotonically unique and never 0
    uint32_t id_a = TokenStreamReader::NextStreamId();
    uint32_t id_b = TokenStreamReader::NextStreamId();
    CHECK(id_a != 0 && id_b != 0 && id_a != id_b);

    // ── Happy path: producer thread emits tokens, reader assembles lines ──
    {
        const uint32_t sid = TokenStreamReader::NextStreamId();
        std::thread producer([&]() {
            ring.write_frame(StreamFrameType::Token, sid, "line one\nli");
            ring.write_frame(StreamFrameType::Token, sid, "ne two\npartial");
            ring.write_frame(StreamFrameType::End, sid, "{\"cancelled\": false}");
        });

        std::vector<std::string> lines;
        TokenStreamReader reader(ring, [&](const std::string& l) { lines.push_back(l); });
        neuroshell::StreamResult r = reader.Consume(sid);
        producer.join();

        CHECK(r.completed);
        CHECK(!r.cancelled && !r.error && !r.timed_out);
        CHECK(r.tokens == 2);
        CHECK(r.full_text == "line one\nline two\npartial");
        CHECK(lines.size() == 3); // 2 newline-terminated + final unterminated
        CHECK(lines[0] == "line one");
        CHECK(lines[1] == "line two");
        CHECK(lines[2] == "partial");
    }

    // ── Stale frames from an old stream id are silently dropped ──
    {
        const uint32_t old_sid = TokenStreamReader::NextStreamId();
        const uint32_t sid = TokenStreamReader::NextStreamId();
        ring.write_frame(StreamFrameType::Token, old_sid, "LEAKED FROM CANCELLED STREAM");
        ring.write_frame(StreamFrameType::Token, sid, "fresh token");
        ring.write_frame(StreamFrameType::End, sid, "{}");

        std::string joined;
        TokenStreamReader reader(ring, [&](const std::string& l) { joined += l; });
        neuroshell::StreamResult r = reader.Consume(sid);
        CHECK(r.completed);
        CHECK(r.full_text == "fresh token");
        CHECK(joined.find("LEAKED") == std::string::npos);
    }

    // ── ERROR frame surfaces the message and stops the stream ──
    {
        const uint32_t sid = TokenStreamReader::NextStreamId();
        ring.write_frame(StreamFrameType::Token, sid, "some ");
        ring.write_frame(StreamFrameType::Error, sid, "provider exploded");
        TokenStreamReader reader(ring, [](const std::string&) {});
        neuroshell::StreamResult r = reader.Consume(sid);
        CHECK(r.error);
        CHECK(!r.completed);
        CHECK(r.error_message == "provider exploded");
    }

    // ── Cooperative cancel: poll_cancel fires → cancel id published,
    //    producer acks with END{"cancelled": true} ──
    {
        const uint32_t sid = TokenStreamReader::NextStreamId();
        ring.clear_cancel();

        std::thread producer([&]() {
            ring.write_frame(StreamFrameType::Token, sid, "tok1 ");
            // simulate daemon polling cancel between tokens
            for (int i = 0; i < 3000 && ring.cancel_requested() != sid; ++i)
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            ring.write_frame(StreamFrameType::End, sid, "{\"cancelled\": true}");
        });

        int polls = 0;
        TokenStreamReader reader(
            ring, [](const std::string&) {},
            [&]() { return ++polls > 3; }); // "Esc" after a few polls
        neuroshell::StreamResult r = reader.Consume(sid);
        producer.join();
        ring.clear_cancel();

        CHECK(r.cancelled);
        CHECK(r.completed); // daemon terminated the stream cleanly
    }

    // ── END carrying cancelled:true (daemon-side cancel detection) ──
    {
        const uint32_t sid = TokenStreamReader::NextStreamId();
        ring.write_frame(StreamFrameType::End, sid, "{\"cancelled\": true, \"tokens\": 0}");
        TokenStreamReader reader(ring, [](const std::string&) {});
        neuroshell::StreamResult r = reader.Consume(sid);
        CHECK(r.completed);
        CHECK(r.cancelled);
    }
}

// ═══════════════════════════════════════════════════════════
// Phase 3: SQLite+FTS5 history with ranked recall (v5.11)
// ═══════════════════════════════════════════════════════════

static void TestFrecencyScoring() {
    using neuroshell::HistoryEngine;
    const int64_t now = 1700000000;

    // More uses ⇒ higher score (same recency)
    double s1 = HistoryEngine::FrecencyScore(1, now, now);
    double s10 = HistoryEngine::FrecencyScore(10, now, now);
    CHECK(s10 > s1);

    // Fresher ⇒ higher score (same uses)
    double fresh = HistoryEngine::FrecencyScore(5, now, now);
    double day_old = HistoryEngine::FrecencyScore(5, now - 86400, now);
    double week_old = HistoryEngine::FrecencyScore(5, now - 7 * 86400, now);
    CHECK(fresh > day_old);
    CHECK(day_old > week_old);

    // Half-life property: score halves every 72h
    double at_0 = HistoryEngine::FrecencyScore(5, now, now);
    double at_half = HistoryEngine::FrecencyScore(5, now - 72 * 3600, now);
    CHECK(at_half > at_0 * 0.49 && at_half < at_0 * 0.51);

    // Degenerate inputs
    CHECK(HistoryEngine::FrecencyScore(0, now, now) == 0.0);
    CHECK(HistoryEngine::FrecencyScore(5, now + 100, now) > 0.0); // future ts clamped
}

static void TestFtsQuerySanitization() {
    using neuroshell::HistoryEngine;

    // Tokens are quote-wrapped, last gets prefix star
    CHECK(HistoryEngine::FtsPrefixQuery("git pu") == "\"git\" \"pu\"*");
    CHECK(HistoryEngine::FtsPrefixQuery("docker") == "\"docker\"*");

    // FTS5 operators in user input are inert (quoted as plain tokens)
    CHECK(HistoryEngine::FtsPrefixQuery("a OR b") == "\"a\" \"OR\" \"b\"*");
    CHECK(HistoryEngine::FtsPrefixQuery("NEAR(x y)") == "\"NEAR(x\" \"y)\"*");

    // Embedded quotes are stripped — cannot escape the wrapper
    CHECK(HistoryEngine::FtsPrefixQuery("a\"b\" OR 1") == "\"ab\" \"OR\" \"1\"*");
    CHECK(HistoryEngine::FtsPrefixQuery("") == "");
    CHECK(HistoryEngine::FtsPrefixQuery("   ") == "");

    // LIKE pattern escaping
    CHECK(HistoryEngine::LikePattern("50%_x") == "%50\\%\\_x%");
    CHECK(HistoryEngine::LikePattern("a\\b") == "%a\\\\b%");
}

static void TestHistoryEngine() {
    using neuroshell::HistoryEngine;
    using neuroshell::RankedCommand;

    if (!neuroshell::sqlite::available()) {
        std::printf("SKIP history engine (no system sqlite3 library)\n");
        return;
    }

    const std::filesystem::path dir = "/tmp/ns_hist_test";
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    const std::filesystem::path db = dir / "history.db";

    HistoryEngine h;
    CHECK(h.Open(db));
    CHECK(h.IsOpen());
    CHECK(!h.LibVersion().empty());

    // ── Append + count + recall ──
    CHECK(h.Append("git status", "/repo/a"));
    CHECK(h.Append("git status", "/repo/a"));
    CHECK(h.Append("git status", "/repo/a"));
    CHECK(h.Append("git push origin main", "/repo/a"));
    CHECK(h.Append("docker compose up", "/repo/b"));
    CHECK(h.Append("docker compose up", "/repo/b"));
    CHECK(!h.Append("", "/x")); // empty command refused
    CHECK(h.Count() == 6);

    // ── cwd affinity: same query, different directories, different winner ──
    {
        auto in_a = h.Search("", "/repo/a", 5);
        CHECK(!in_a.empty());
        if (!in_a.empty()) CHECK(in_a[0].command == "git status"); // 3 uses, all in /repo/a

        auto in_b = h.Search("", "/repo/b", 5);
        CHECK(!in_b.empty());
        if (!in_b.empty()) CHECK(in_b[0].command == "docker compose up"); // cwd affinity beats raw frequency
    }

    // ── FTS prefix search ──
    {
        auto git = h.Search("git", "/repo/a", 5);
        CHECK(git.size() == 2);
        if (!git.empty()) {
            CHECK(git[0].command == "git status");
            CHECK(git[0].uses == 3);
        }

        auto push = h.Search("git pu", "/repo/a", 5);
        CHECK(push.size() == 1);
        if (!push.empty()) CHECK(push[0].command == "git push origin main");

        // No match
        CHECK(h.Search("kubectl", "/repo/a", 5).empty());
    }

    // ── Hostile queries: FTS operators + SQL metachars are inert ──
    {
        auto q1 = h.Search("git OR docker", "/", 5);      // OR is a quoted token, matches nothing
        CHECK(q1.empty());
        auto q2 = h.Search("'; DROP TABLE commands;--", "/", 5);
        CHECK(q2.empty());
        CHECK(h.Count() == 6); // table intact
        auto q3 = h.Search("\"unbalanced", "/", 5);
        CHECK(q3.empty()); // no crash, quotes stripped
    }

    // ── RecentUnique dedupes and orders newest-first ──
    {
        auto recent = h.RecentUnique(10);
        CHECK(recent.size() == 3);
        if (!recent.empty()) CHECK(recent[0] == "docker compose up"); // most recent append
    }

    // ── Legacy flat-file migration: once and only once ──
    {
        const std::filesystem::path txt = dir / "history.txt";
        {
            std::ofstream f(txt);
            f << "ls -la\nmake test\nls -la\n";
        }
        int imported = h.MigrateLegacyFile(txt);
        CHECK(imported == 3);
        CHECK(h.Count() == 6 + 3 + 1); // +1 marker row
        int again = h.MigrateLegacyFile(txt);
        CHECK(again == 0); // marker prevents re-import
        auto ls = h.Search("ls", "/", 5);
        CHECK(!ls.empty());
        if (!ls.empty()) { // guard: CHECK records failure but doesn't abort
            CHECK(ls[0].command == "ls -la");
            CHECK(ls[0].uses == 2);
        }
    }

    // ── Concurrent second connection (daemon simulation): WAL + busy_timeout ──
    {
        HistoryEngine peer;
        CHECK(peer.Open(db));
        CHECK(peer.Append("from-the-daemon", "/repo/c"));
        auto seen = h.Search("from-the-daemon", "/repo/c", 5);
        CHECK(seen.size() == 1); // host sees the daemon's write immediately
        peer.Close();
    }

    // ── Prefix beats substring at equal frecency ──
    {
        HistoryEngine h2;
        const std::filesystem::path db2 = dir / "prefix.db";
        CHECK(h2.Open(db2));
        CHECK(h2.Append("status-checker run", "/w"));
        CHECK(h2.Append("git status", "/w"));
        auto r = h2.Search("status", "/w", 5);
        CHECK(r.size() == 2);
        if (!r.empty()) CHECK(r[0].command == "status-checker run"); // prefix match outranks
        h2.Close();
    }

    // ── Unopened engine degrades to empty/no-op, never crashes ──
    {
        HistoryEngine cold;
        CHECK(!cold.IsOpen());
        CHECK(!cold.Append("x", "/"));
        CHECK(cold.Search("x", "/", 5).empty());
        CHECK(cold.RecentUnique(5).empty());
        CHECK(cold.Count() == -1);
        CHECK(cold.MigrateLegacyFile("/nonexistent") == 0);
    }

    h.Close();
    CHECK(!h.IsOpen());
    std::filesystem::remove_all(dir);
}

// ═══════════════════════════════════════════════════════════
// Phase 4: blast-radius preview (v5.12)
// ═══════════════════════════════════════════════════════════

static void TestBlastShellParsing() {
    using neuroshell::BlastRadiusAnalyzer;

    // Segment splitting on | ; && || — quote-aware
    {
        auto s = BlastRadiusAnalyzer::SplitSegments("ls | grep x && rm y; echo z || cat w");
        CHECK(s.size() == 5);
        CHECK(s[0] == "ls");
        CHECK(s[2] == "rm y");
        CHECK(s[4] == "cat w");
    }
    {
        auto s = BlastRadiusAnalyzer::SplitSegments("echo 'a | b; c' && ls \"d && e\"");
        CHECK(s.size() == 2);
        CHECK(s[0] == "echo 'a | b; c'");
        CHECK(s[1] == "ls \"d && e\"");
    }

    // Tokenizer: quotes, escapes, redirections
    {
        auto t = BlastRadiusAnalyzer::Tokenize("rm -rf 'my dir' \"other dir\" plain\\ file");
        CHECK(t.size() == 5);
        CHECK(t[1] == "-rf");
        CHECK(t[2] == "my dir");
        CHECK(t[3] == "other dir");
        CHECK(t[4] == "plain file");
    }
    {
        auto t = BlastRadiusAnalyzer::Tokenize("echo hi > out.txt");
        CHECK(t.size() == 4);
        CHECK(t[2] == ">");
        CHECK(t[3] == "out.txt");
    }
    {
        auto t = BlastRadiusAnalyzer::Tokenize("cmd 2> err.log >> app.log");
        CHECK(t.size() == 5);
        CHECK(t[1] == ">");   // fd digit folded into the operator
        CHECK(t[2] == "err.log");
        CHECK(t[3] == ">>");
        CHECK(t[4] == "app.log");
    }

    // Path policy helpers
    CHECK(BlastRadiusAnalyzer::IsSystemCriticalPath("/"));
    CHECK(BlastRadiusAnalyzer::IsSystemCriticalPath("/etc"));
    CHECK(BlastRadiusAnalyzer::IsSystemCriticalPath("/usr/"));
    CHECK(!BlastRadiusAnalyzer::IsSystemCriticalPath("/etc/myapp"));
    CHECK(!BlastRadiusAnalyzer::IsSystemCriticalPath("/tmp/x"));
    const char* home = std::getenv("HOME");
    if (home) CHECK(BlastRadiusAnalyzer::IsSystemCriticalPath(home));

    CHECK(BlastRadiusAnalyzer::IsBlockDevicePath("/dev/sda"));
    CHECK(BlastRadiusAnalyzer::IsBlockDevicePath("/dev/nvme0n1"));
    CHECK(!BlastRadiusAnalyzer::IsBlockDevicePath("/dev/null"));
    CHECK(!BlastRadiusAnalyzer::IsBlockDevicePath("/dev/urandom"));
    CHECK(!BlastRadiusAnalyzer::IsBlockDevicePath("/tmp/dev/sda"));
}

static void TestBlastRadiusAnalyzer() {
    using neuroshell::BlastRadiusAnalyzer;
    using neuroshell::BlastReport;
    using neuroshell::BlastSeverity;
    namespace fs = std::filesystem;

    // Sandbox tree: 3 files (one 2 MiB), a subdir, a symlink
    const fs::path dir = "/tmp/ns_blast_test";
    fs::remove_all(dir);
    fs::create_directories(dir / "sub");
    { std::ofstream f(dir / "a.txt"); f << "hello"; }
    { std::ofstream f(dir / "b.log"); f << std::string(2 * 1024 * 1024, 'x'); }
    { std::ofstream f(dir / "sub" / "c.txt"); f << "world"; }
    std::error_code ec;
    fs::create_symlink(dir / "a.txt", dir / "link_a", ec);

    BlastRadiusAnalyzer az;
    const std::string cwd = dir.string();

    // ── Measure: file vs dir vs symlink vs missing ──
    {
        auto t = az.Measure(dir / "a.txt");
        CHECK(t.exists && !t.is_dir && t.files == 1 && t.bytes == 5);
        auto d = az.Measure(dir);
        CHECK(d.exists && d.is_dir);
        CHECK(d.files == 4);                      // a, b, sub/c, link_a
        CHECK(d.bytes >= 2 * 1024 * 1024);
        auto l = az.Measure(dir / "link_a");
        CHECK(l.exists && l.files == 1 && l.bytes == 0); // link counted, not followed
        auto m = az.Measure(dir / "nope");
        CHECK(!m.exists && m.files == 0);
    }

    // ── Glob resolution ──
    {
        auto ts = az.ResolveTargets("*.txt", cwd);
        CHECK(ts.size() == 1);
        if (!ts.empty()) CHECK(ts[0].path.find("a.txt") != std::string::npos);
        auto all = az.ResolveTargets("*", cwd);
        CHECK(all.size() == 4);
        auto none = az.ResolveTargets("*.zip", cwd);
        CHECK(none.size() == 1 && !none[0].exists); // no match → reported missing
    }

    // ── Severity: safe commands are NONE (zero friction) ──
    for (const char* safe : {"ls -la", "git status", "echo hello", "cat a.txt",
                             "grep -r foo .", "make test", "rm nonexistent.xyz"}) {
        BlastReport r = az.Analyze(safe, cwd);
        CHECK(!r.NeedsConfirmation());
    }

    // ── rm of an existing file ⇒ MEDIUM with byte counts ──
    {
        BlastReport r = az.Analyze("rm b.log", cwd);
        CHECK(r.severity == BlastSeverity::Medium);
        CHECK(r.NeedsConfirmation());
        CHECK(r.total_files == 1);
        CHECK(r.total_bytes >= 2 * 1024 * 1024);
    }

    // ── rm -rf on the sandbox dir ⇒ MEDIUM (4 files) with full counts ──
    {
        BlastReport r = az.Analyze("rm -rf " + dir.string(), "/");
        CHECK(r.severity == BlastSeverity::Medium);
        CHECK(r.total_files == 4);
    }

    // ── rm -rf / and ~ ⇒ CRITICAL regardless of counts ──
    {
        CHECK(az.Analyze("rm -rf /", cwd).severity == BlastSeverity::Critical);
        CHECK(az.Analyze("sudo rm -rf /etc", cwd).severity == BlastSeverity::Critical);
        if (std::getenv("HOME"))
            CHECK(az.Analyze("rm -rf ~", cwd).severity == BlastSeverity::Critical);
    }

    // ── dd onto a block device ⇒ CRITICAL; onto a file ⇒ MEDIUM ──
    {
        CHECK(az.Analyze("dd if=/dev/zero of=/dev/sda bs=1M", cwd).severity ==
              BlastSeverity::Critical);
        CHECK(az.Analyze("dd if=a.txt of=copy.bin", cwd).severity == BlastSeverity::Medium);
        CHECK(az.Analyze("dd if=/dev/urandom of=/dev/null", cwd).severity !=
              BlastSeverity::Critical);
    }

    // ── mkfs ⇒ CRITICAL ──
    CHECK(az.Analyze("mkfs.ext4 /dev/sdb1", cwd).severity == BlastSeverity::Critical);

    // ── git destructive verbs ⇒ HIGH; benign git ⇒ NONE ──
    {
        CHECK(az.Analyze("git clean -fd", cwd).severity == BlastSeverity::High);
        CHECK(az.Analyze("git reset --hard HEAD~3", cwd).severity == BlastSeverity::High);
        CHECK(az.Analyze("git push --force origin main", cwd).severity == BlastSeverity::High);
        CHECK(az.Analyze("git branch -D feature", cwd).severity == BlastSeverity::High);
        CHECK(az.Analyze("git reset --soft HEAD~1", cwd).severity == BlastSeverity::None);
        CHECK(az.Analyze("git clean -n", cwd).severity == BlastSeverity::None);
        CHECK(az.Analyze("git branch -d merged", cwd).severity == BlastSeverity::None);
    }

    // ── find -delete ⇒ flagged; plain find ⇒ NONE ──
    {
        CHECK(az.Analyze("find . -name '*.tmp' -delete", cwd).NeedsConfirmation());
        CHECK(!az.Analyze("find . -name '*.tmp'", cwd).NeedsConfirmation());
    }

    // ── > truncation of a non-empty file ⇒ MEDIUM; new/empty file ⇒ NONE ──
    {
        CHECK(az.Analyze("echo fresh > b.log", cwd).severity == BlastSeverity::Medium);
        CHECK(az.Analyze("echo x > brand_new.txt", cwd).severity == BlastSeverity::None);
        CHECK(az.Analyze("echo x >> b.log", cwd).severity == BlastSeverity::None); // append is safe
    }

    // ── mv/cp over an existing file ⇒ MEDIUM; to a new name ⇒ NONE ──
    {
        CHECK(az.Analyze("mv a.txt b.log", cwd).severity == BlastSeverity::Medium);
        CHECK(az.Analyze("cp a.txt fresh_name.txt", cwd).severity == BlastSeverity::None);
    }

    // ── chmod -R on system path ⇒ CRITICAL; on sandbox ⇒ MEDIUM ──
    {
        CHECK(az.Analyze("chmod -R 777 /", cwd).severity == BlastSeverity::Critical);
        CHECK(az.Analyze("chmod -R 755 sub", cwd).severity == BlastSeverity::Medium);
        CHECK(az.Analyze("chmod 644 a.txt", cwd).severity == BlastSeverity::None); // non-recursive
    }

    // ── Destructive op hidden mid-pipeline is still caught ──
    {
        BlastReport r = az.Analyze("ls -la && rm -rf sub | echo done", cwd);
        CHECK(r.NeedsConfirmation());
    }

    // ── Scan caps: tiny budget forces the capped flag ──
    {
        BlastRadiusAnalyzer tiny;
        tiny.max_inodes = 2;
        auto t = tiny.Measure(dir);
        CHECK(t.scan_capped);
        BlastReport r = tiny.Analyze("rm -rf " + dir.string(), "/");
        CHECK(r.severity == BlastSeverity::High); // capped ⇒ assume the worst
        CHECK(r.scan_capped);
    }

    // ── Quoted paths with spaces resolve correctly ──
    {
        fs::create_directories(dir / "my dir");
        { std::ofstream f(dir / "my dir" / "f.txt"); f << "x"; }
        BlastReport r = az.Analyze("rm -rf 'my dir'", cwd);
        CHECK(r.NeedsConfirmation());
        CHECK(r.total_files == 1);
    }

    fs::remove_all(dir);
}

// ═══════════════════════════════════════════════════════════
// Phase 5: universal undo (v5.13)
// ═══════════════════════════════════════════════════════════

static std::string ReadWholeFile(const std::filesystem::path& p) {
    std::ifstream f(p, std::ios::binary);
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static void TestUndoManifestEscaping() {
    using neuroshell::UndoEscape;
    using neuroshell::UndoUnescape;
    CHECK(UndoEscape("plain") == "plain");
    CHECK(UndoEscape("a\tb\nc\\d") == "a\\tb\\nc\\\\d");
    const std::vector<std::string> roundtrips = {
        "plain", "a\tb", "x\ny", "back\\slash", "mix\t\\\n\t\\end", ""};
    for (const std::string& s : roundtrips) {
        CHECK(UndoUnescape(UndoEscape(s)) == s);
    }
}

static void TestUndoEngine() {
    namespace fs = std::filesystem;
    using neuroshell::BlastRadiusAnalyzer;
    using neuroshell::BlastReport;
    using neuroshell::SnapshotStatus;
    using neuroshell::UndoEngine;

    const fs::path work = "/tmp/ns_undo_work";
    const fs::path undoRoot = "/tmp/ns_undo_root";
    fs::remove_all(work);
    fs::remove_all(undoRoot);
    fs::create_directories(work / "proj" / "src");
    { std::ofstream f(work / "proj" / "src" / "main.c"); f << "int main(){}"; }
    { std::ofstream f(work / "proj" / "README.md"); f << "# readme"; }
    { std::ofstream f(work / "loose.txt"); f << "loose-content"; }
    std::error_code ec;
    fs::create_symlink("README.md", work / "proj" / "link.md", ec);

    BlastRadiusAnalyzer az;
    UndoEngine eng(undoRoot);

    // ── 1. Snapshot a directory delete, actually delete, undo restores ──
    {
        BlastReport rep = az.Analyze("rm -rf proj", work.string());
        CHECK(rep.NeedsConfirmation());
        auto snap = eng.SnapshotBeforeExecute(rep, "rm -rf proj", work.string());
        CHECK(snap.status == SnapshotStatus::Saved);
        CHECK(snap.files == 3); // main.c, README.md, link.md

        fs::remove_all(work / "proj");
        CHECK(!fs::exists(work / "proj"));

        auto r = eng.Undo();
        CHECK(r.ok);
        CHECK(r.files_restored == 3);
        CHECK(ReadWholeFile(work / "proj" / "src" / "main.c") == "int main(){}");
        CHECK(ReadWholeFile(work / "proj" / "README.md") == "# readme");
        CHECK(fs::is_symlink(work / "proj" / "link.md"));
        // Transaction consumed after successful restore
        CHECK(eng.ListTransactions().empty());
    }

    // ── 2. Single-file snapshot; undo restores content after overwrite ──
    {
        BlastReport rep = az.Analyze("rm loose.txt", work.string());
        auto snap = eng.SnapshotBeforeExecute(rep, "rm loose.txt", work.string());
        CHECK(snap.status == SnapshotStatus::Saved);
        CHECK(snap.files == 1);

        { std::ofstream f(work / "loose.txt", std::ios::trunc); f << "clobbered"; }
        auto r = eng.Undo();
        CHECK(r.ok);
        CHECK(ReadWholeFile(work / "loose.txt") == "loose-content");
    }

    // ── 3. Nothing to save: nonexistent target → skip, no txn dir ──
    {
        BlastReport rep = az.Analyze("rm ghost_file.xyz", work.string());
        auto snap = eng.SnapshotBeforeExecute(rep, "rm ghost_file.xyz", work.string());
        CHECK(snap.status == SnapshotStatus::SkippedNothingToSave);
        CHECK(eng.ListTransactions().empty());
    }

    // ── 4. Copy budget: no reflink + tiny cap ⇒ SkippedTooLarge, dir cleaned ──
    {
        { std::ofstream f(work / "big.bin"); f << std::string(4096, 'B'); }
        UndoEngine tiny(undoRoot);
        tiny.allow_reflink = false;
        tiny.max_copy_bytes = 1024;
        BlastReport rep = az.Analyze("rm big.bin", work.string());
        auto snap = tiny.SnapshotBeforeExecute(rep, "rm big.bin", work.string());
        CHECK(snap.status == SnapshotStatus::SkippedTooLarge);
        CHECK(tiny.ListTransactions().empty());
        // No leftover partial txn directories
        size_t dirs = 0;
        if (fs::is_directory(undoRoot))
            for (auto& d : fs::directory_iterator(undoRoot)) { (void)d; ++dirs; }
        CHECK(dirs == 0);
    }

    // ── 5. Inode budget pre-check ⇒ skip before any copying ──
    {
        UndoEngine capped(undoRoot);
        capped.max_snapshot_inodes = 1;
        BlastReport rep = az.Analyze("rm -rf proj", work.string());
        auto snap = capped.SnapshotBeforeExecute(rep, "rm -rf proj", work.string());
        CHECK(snap.status == SnapshotStatus::SkippedTooLarge);
    }

    // ── 6. Manifest durability: tab/newline in command round-trips ──
    {
        BlastReport rep = az.Analyze("rm loose.txt", work.string());
        std::string weird = "rm\t'loose.txt'\n# comment";
        auto snap = eng.SnapshotBeforeExecute(rep, weird, work.string());
        CHECK(snap.status == SnapshotStatus::Saved);
        auto txns = eng.ListTransactions();
        CHECK(txns.size() == 1);
        if (!txns.empty()) CHECK(txns[0].command == weird);
        CHECK(eng.Undo().ok);
    }

    // ── 7. Incomplete manifest is never restored; GC sweeps corpses ──
    {
        fs::create_directories(undoRoot / "txn-999999999999999" / "data");
        {
            std::ofstream m(undoRoot / "txn-999999999999999" / "manifest");
            m << "neuroshell-undo v1\nid\ttxn-999999999999999\n"; // no `complete`
        }
        fs::create_directories(undoRoot / "txn-888888888888888"); // no manifest at all
        CHECK(eng.ListTransactions().empty());
        eng.GarbageCollect();
        CHECK(!fs::exists(undoRoot / "txn-888888888888888"));
    }

    // ── 8. LIFO ordering: newest transaction is undone first ──
    {
        { std::ofstream f(work / "first.txt"); f << "v1"; }
        { std::ofstream f(work / "second.txt"); f << "v2"; }
        BlastReport r1 = az.Analyze("rm first.txt", work.string());
        CHECK(eng.SnapshotBeforeExecute(r1, "rm first.txt", work.string()).status ==
              SnapshotStatus::Saved);
        std::this_thread::sleep_for(std::chrono::milliseconds(2)); // distinct µs ids
        BlastReport r2 = az.Analyze("rm second.txt", work.string());
        CHECK(eng.SnapshotBeforeExecute(r2, "rm second.txt", work.string()).status ==
              SnapshotStatus::Saved);

        auto txns = eng.ListTransactions();
        CHECK(txns.size() == 2);
        if (txns.size() == 2) CHECK(txns[0].command == "rm second.txt");

        fs::remove(work / "second.txt");
        auto r = eng.Undo();
        CHECK(r.ok && r.command == "rm second.txt");
        CHECK(fs::exists(work / "second.txt"));
        CHECK(eng.ListTransactions().size() == 1);
        CHECK(eng.Undo().ok); // consume the older one too
    }

    // ── 9. GC count budget evicts oldest ──
    {
        UndoEngine gcEng(undoRoot);
        gcEng.gc_max_transactions = 2;
        for (int i = 0; i < 4; ++i) {
            { std::ofstream f(work / "gcfile.txt"); f << "gen" << i; }
            BlastReport rep = az.Analyze("rm gcfile.txt", work.string());
            CHECK(gcEng.SnapshotBeforeExecute(rep, "rm gcfile.txt #" + std::to_string(i),
                                              work.string()).status == SnapshotStatus::Saved);
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
        }
        gcEng.GarbageCollect();
        CHECK(gcEng.ListTransactions().size() <= 2);
    }

    // ── 10. Undo with empty store fails gracefully ──
    {
        UndoEngine empty("/tmp/ns_undo_empty_root");
        fs::remove_all("/tmp/ns_undo_empty_root");
        auto r = empty.Undo();
        CHECK(!r.ok);
        CHECK(r.error == "nothing to undo");
    }

    // ── 11. Restored file keeps its permission bits ──
    {
        fs::path script = work / "run.sh";
        { std::ofstream f(script); f << "#!/bin/sh\necho ok\n"; }
        fs::permissions(script, fs::perms::owner_all | fs::perms::group_read |
                                fs::perms::others_read);
        BlastReport rep = az.Analyze("rm run.sh", work.string());
        CHECK(eng.SnapshotBeforeExecute(rep, "rm run.sh", work.string()).status ==
              SnapshotStatus::Saved);
        fs::remove(script);
        CHECK(eng.Undo().ok);
        auto perms = fs::status(script).permissions();
        CHECK((perms & fs::perms::owner_exec) != fs::perms::none);
    }

    fs::remove_all(work);
    fs::remove_all(undoRoot);
    fs::remove_all("/tmp/ns_undo_empty_root");
}

// ═══════════════════════════════════════════════════════════
// Phase 8: kernel sandbox (v5.16)
// ═══════════════════════════════════════════════════════════

static void TestSandboxPolicy() {
    using neuroshell::SandboxMode;
    using neuroshell::ShouldSandbox;
    using neuroshell::ParseSandboxMode;

    // Mode parsing round-trips
    SandboxMode m;
    CHECK(ParseSandboxMode("off", m) && m == SandboxMode::Off);
    CHECK(ParseSandboxMode("project", m) && m == SandboxMode::Project);
    CHECK(ParseSandboxMode("strict", m) && m == SandboxMode::Strict);
    CHECK(!ParseSandboxMode("bogus", m));
    CHECK(!ParseSandboxMode("", m));
    CHECK(std::string(neuroshell::SandboxModeName(SandboxMode::Off)) == "off");
    CHECK(std::string(neuroshell::SandboxModeName(SandboxMode::Project)) == "project");
    CHECK(std::string(neuroshell::SandboxModeName(SandboxMode::Strict)) == "strict");

    // Policy matrix: (mode, aiTranslated, escalated) → confined?
    CHECK(!ShouldSandbox(SandboxMode::Off, false, false));
    CHECK(!ShouldSandbox(SandboxMode::Off, true, false));
    CHECK(!ShouldSandbox(SandboxMode::Project, false, false)); // user-typed: free
    CHECK(ShouldSandbox(SandboxMode::Project, true, false));   // AI path: confined
    CHECK(ShouldSandbox(SandboxMode::Strict, false, false));
    CHECK(ShouldSandbox(SandboxMode::Strict, true, false));
    // `!` escalation always wins
    CHECK(!ShouldSandbox(SandboxMode::Project, true, true));
    CHECK(!ShouldSandbox(SandboxMode::Strict, true, true));

    // Step names are all mapped
    for (int s = neuroshell::SBX_OK; s <= neuroshell::SBX_ERR_UNSUPPORTED; ++s)
        CHECK(std::string(neuroshell::SandboxStepName(s)) != "unknown");
}

static void TestSandboxPrepare() {
    using neuroshell::PreparedSandbox;
    using neuroshell::SandboxSpec;

    // Disabled spec prepares to a no-op
    {
        SandboxSpec spec;
        spec.enabled = false;
        PreparedSandbox p = PreparedSandbox::Prepare(spec);
        CHECK(!p.enabled);
        CHECK(p.ApplyInChild() == neuroshell::SBX_OK); // no-op in-process is safe
    }

    // Enabled spec: rw paths deduplicated, device files auto-added
    {
        SandboxSpec spec;
        spec.enabled = true;
        spec.project_dir = "/tmp";
        spec.rw_paths.push_back("/tmp");          // duplicate of project_dir
        spec.rw_paths.push_back("/var/tmp");
        PreparedSandbox p = PreparedSandbox::Prepare(spec);
        CHECK(p.enabled);
        size_t tmpCount = 0;
        bool hasDevNull = false, hasVarTmp = false;
        for (const auto& e : p.rw_paths) {
            if (e == "/tmp") ++tmpCount;
            if (e == "/dev/null") hasDevNull = true;
            if (e == "/var/tmp") hasVarTmp = true;
        }
        CHECK(tmpCount == 1);       // deduplicated
        CHECK(hasDevNull);          // device files auto-added
        CHECK(hasVarTmp);
#if defined(__linux__)
        neuroshell::SandboxSupport sup = neuroshell::ProbeSandboxSupport();
        if (sup.seccomp) CHECK(!p.bpf.empty());
        if (sup.landlock) {
            CHECK(p.landlock_available);
            CHECK(p.landlock_abi >= 1);
        }
#endif
    }
}

#if defined(__linux__)
// Fork a child, apply the sandbox, run `cmd` through /bin/sh, return exit code.
static int RunConfined(const neuroshell::PreparedSandbox& p, const std::string& cmd) {
    pid_t pid = fork();
    if (pid == 0) {
        int devnull = open("/dev/null", O_WRONLY);
        if (devnull >= 0) { dup2(devnull, 1); dup2(devnull, 2); close(devnull); }
        int rc = p.ApplyInChild();
        if (rc != neuroshell::SBX_OK) _exit(90 + rc);
        execl("/bin/sh", "sh", "-c", cmd.c_str(), (char*)NULL);
        _exit(127);
    }
    int st = 0;
    waitpid(pid, &st, 0);
    return WIFEXITED(st) ? WEXITSTATUS(st) : 128;
}

static void TestSandboxKernelEnforcement() {
    namespace fs = std::filesystem;
    neuroshell::SandboxSupport sup = neuroshell::ProbeSandboxSupport();
    if (!sup.landlock) {
        // Kernel without Landlock: enforcement tests are not runnable here.
        // The fail-closed path is still verifiable.
        neuroshell::SandboxSpec spec;
        spec.enabled = true;
        spec.fail_closed = true;
        spec.project_dir = "/tmp";
        neuroshell::PreparedSandbox p = neuroshell::PreparedSandbox::Prepare(spec);
        CHECK(RunConfined(p, "true") == 90 + neuroshell::SBX_ERR_UNSUPPORTED);
        return;
    }

    const fs::path proj = "/tmp/ns_sbx_proj";
    const fs::path outside = "/tmp/ns_sbx_outside";
    fs::remove_all(proj);
    fs::remove_all(outside);
    fs::create_directories(proj);
    fs::create_directories(outside);
    { std::ofstream f(outside / "keep.txt"); f << "precious"; }

    neuroshell::SandboxSpec spec;
    spec.enabled = true;
    spec.project_dir = proj.string();
    neuroshell::PreparedSandbox p = neuroshell::PreparedSandbox::Prepare(spec);
    CHECK(p.landlock_available);

    // 1. Write INSIDE the project dir → allowed
    CHECK(RunConfined(p, "echo ok > " + (proj / "inside.txt").string()) == 0);
    CHECK(fs::exists(proj / "inside.txt"));

    // 2. Write OUTSIDE → kernel EACCES (nonzero exit, file not created)
    CHECK(RunConfined(p, "echo evil > " + (outside / "pwned.txt").string()) != 0);
    CHECK(!fs::exists(outside / "pwned.txt"));

    // 3. rm OUTSIDE → denied by the kernel, file survives
    CHECK(RunConfined(p, "rm " + (outside / "keep.txt").string()) != 0);
    CHECK(fs::exists(outside / "keep.txt"));

    // 4. Read anywhere → allowed (read+exec on whole tree)
    CHECK(RunConfined(p, "head -c1 /etc/passwd > /dev/null") == 0);

    // 5. Exec system binaries → allowed
    CHECK(RunConfined(p, "ls /usr/bin > /dev/null") == 0);

    // 6. /dev/null writable inside the sandbox (file-only Landlock rule)
    CHECK(RunConfined(p, "echo discard > /dev/null") == 0);

    // 7. /tmp NOT writable when it isn't in rw_paths (only proj is)
    //    — write to a fresh path directly under /tmp
    CHECK(RunConfined(p, "echo x > /tmp/ns_sbx_probe_direct.txt") != 0);
    CHECK(!fs::exists("/tmp/ns_sbx_probe_direct.txt"));

    // 8. seccomp: chroot fails with EPERM (readable error), not a signal
    if (sup.seccomp) {
        int rc = RunConfined(p, "cd " + proj.string() +
                                " && /usr/sbin/chroot . /bin/sh -c true");
        CHECK(rc != 0);
        CHECK(rc < 128);   // EPERM error path, not SIGSYS kill
    }

    // 9. Extra rw_paths grant write access where specified
    {
        neuroshell::SandboxSpec spec2;
        spec2.enabled = true;
        spec2.project_dir = proj.string();
        spec2.rw_paths.push_back(outside.string());
        neuroshell::PreparedSandbox p2 = neuroshell::PreparedSandbox::Prepare(spec2);
        CHECK(RunConfined(p2, "echo granted > " + (outside / "granted.txt").string()) == 0);
        CHECK(fs::exists(outside / "granted.txt"));
    }

    // 10. Escalation contract: unconfined child CAN write outside
    {
        neuroshell::SandboxSpec off;
        off.enabled = false;
        neuroshell::PreparedSandbox poff = neuroshell::PreparedSandbox::Prepare(off);
        CHECK(RunConfined(poff, "echo free > " + (outside / "free.txt").string()) == 0);
    }

    fs::remove_all(proj);
    fs::remove_all(outside);
}
#endif // __linux__

int main() {
    TestSemver();
    TestValidators();
    TestQuoting();
    TestShmLayout();
    TestShmRoundtrip();
    TestDlpMasker();
    TestRunCapture();
    TestSha2Vectors();
    TestEd25519();
    TestJsonMini();
    TestUpdateVerifier();
    TestStreamFrames();
    TestTokenStreamReader();
    TestFrecencyScoring();
    TestFtsQuerySanitization();
    TestHistoryEngine();
    TestBlastShellParsing();
    TestBlastRadiusAnalyzer();
    TestUndoManifestEscaping();
    TestUndoEngine();
    TestSandboxPolicy();
    TestSandboxPrepare();
#if defined(__linux__)
    TestSandboxKernelEnforcement();
#endif

    std::printf("\n%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
