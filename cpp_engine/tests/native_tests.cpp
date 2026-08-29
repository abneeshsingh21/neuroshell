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
    CHECK(neuroshell::SHM_ABI_VERSION == 2);
    CHECK(offsetof(neuroshell::SHMHeader, write_cursor) == 64);
    CHECK(offsetof(neuroshell::SHMHeader, read_cursor) == 72);
    CHECK(offsetof(neuroshell::SHMHeader, message_sequence) == 80);
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

    std::printf("\n%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
