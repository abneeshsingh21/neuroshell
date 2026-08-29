// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// Native unit tests for the NeuroShell C++ host (no framework dependency).
// Build & run:  cmake -B build && cmake --build build && ctest --test-dir build
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>

#include "version.hpp"
#include "safe_exec.hpp"
#include "shm_ipc.hpp"
#include "dlp_masker.hpp"

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

int main() {
    TestSemver();
    TestValidators();
    TestQuoting();
    TestShmLayout();
    TestShmRoundtrip();
    TestDlpMasker();
    TestRunCapture();

    std::printf("\n%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
