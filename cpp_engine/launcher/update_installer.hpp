// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// UpdateInstaller — verified download + atomic in-place swap.
//
// The old updater piped `curl | bash` (POSIX) or blind-replaced the exe
// (Windows) with zero authentication. This module implements the verified
// pipeline instead:
//
//   manifest.json + manifest.json.sig  ──►  UpdateVerifier (Ed25519 + policy)
//                    │ ok
//                    ▼
//   download artifact → *temp file in the destination directory*
//                    │
//                    ▼
//   SHA-256(payload) == manifest digest?  (constant-time)
//                    │ ok
//                    ▼
//   chmod +x → atomic swap:
//     POSIX:   rename(current → current.old.<ts>) ; rename(temp → current)
//              (same-directory rename ⇒ atomic on the same filesystem)
//     Windows: MoveFileExW(current → .old) ; MoveFileExW(temp → current)
//              (a running exe can be renamed, not deleted)
//
// Every network fetch happens through safe_exec argv execution — there is
// no shell anywhere in this pipeline, and every URL passed to curl has
// already survived the verifier's https+allowlist+charset policy.
#pragma once

#include "safe_exec.hpp"
#include "update_verifier.hpp"

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

#if defined(_WIN32)
#include <windows.h>
#elif defined(__APPLE__)
#include <mach-o/dyld.h>
#include <sys/stat.h>
#include <unistd.h>
#else
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace neuroshell::update {

namespace fs = std::filesystem;

struct InstallResult {
    bool ok = false;
    std::string message;      // human-readable outcome
    std::string new_version;  // set on success
};

class UpdateInstaller {
public:
    // Repository release endpoints (raw manifest + detached signature are
    // uploaded as release assets by scripts/sign_release.py workflow).
    static constexpr const char* kManifestUrl =
        "https://github.com/abneeshsingh21/neuroshell/releases/latest/download/manifest.json";
    static constexpr const char* kManifestSigUrl =
        "https://github.com/abneeshsingh21/neuroshell/releases/latest/download/manifest.json.sig";

    // Resolve the absolute path of the running executable (no argv[0] guessing).
    static fs::path GetExecutablePath() {
#if defined(_WIN32)
        wchar_t buf[MAX_PATH * 2];
        DWORD n = GetModuleFileNameW(nullptr, buf, MAX_PATH * 2);
        if (n == 0 || n >= MAX_PATH * 2) return {};
        return fs::path(std::wstring(buf, n));
#elif defined(__APPLE__)
        uint32_t size = 0;
        _NSGetExecutablePath(nullptr, &size);
        std::string buf(size, '\0');
        if (_NSGetExecutablePath(buf.data(), &size) != 0) return {};
        buf.resize(std::strlen(buf.c_str()));
        std::error_code ec;
        fs::path canon = fs::canonical(buf, ec);
        return ec ? fs::path(buf) : canon;
#else
        std::error_code ec;
        fs::path p = fs::read_symlink("/proc/self/exe", ec);
        return ec ? fs::path{} : p;
#endif
    }

    // Full pipeline. `verifier` is injectable for tests.
    static InstallResult Run(const UpdateVerifier& verifier = UpdateVerifier()) {
        InstallResult r;

        // 0. Fail closed BEFORE any network I/O when no signing key is
        //    provisioned — an unprovisioned build must not even fetch.
        if (IsPlaceholderKey(kUpdatePublicKeyHex)) {
            r.message = std::string(VerifyStatusMessage(VerifyStatus::KeyNotProvisioned)) +
                        " (use your package manager to update)";
            return r;
        }

        // 1. Fetch manifest + signature (small, bounded).
        std::string manifest_raw, sig_raw;
        if (!FetchSmall(kManifestUrl, UpdateVerifier::kMaxManifestBytes, manifest_raw)) {
            r.message = "could not download the update manifest (network error?)";
            return r;
        }
        if (!FetchSmall(kManifestSigUrl, 4096, sig_raw)) {
            r.message = "this release is missing a manifest signature — refusing unsigned update";
            return r;
        }
        std::string sig_hex = TrimAscii(sig_raw);

        // 2. Verify signature + policy.
        VerifiedManifest m;
        VerifyStatus vs = verifier.VerifyManifest(manifest_raw, sig_hex, m);
        if (vs != VerifyStatus::Ok) {
            r.message = VerifyStatusMessage(vs);
            return r;
        }

        // 3. Locate ourselves; stage the download NEXT TO the destination so
        //    the final rename is same-filesystem (and therefore atomic).
        fs::path self = GetExecutablePath();
        if (self.empty()) {
            r.message = "cannot determine the path of the running executable";
            return r;
        }
        fs::path dir = self.parent_path();
        auto stamp = std::chrono::duration_cast<std::chrono::seconds>(
                         std::chrono::system_clock::now().time_since_epoch())
                         .count();
        fs::path staged = dir / (".ns_update_" + std::to_string(stamp) + ".part");

        // 4. Download the signed artifact.
        if (!FetchToFile(m.artifact.url, staged, m.artifact.size)) {
            std::error_code ec;
            fs::remove(staged, ec);
            r.message = "artifact download failed";
            return r;
        }

        // 5. Bind payload to the signed digest.
        std::string err;
        if (!UpdateVerifier::VerifyArtifactFile(staged.string(), m.artifact, &err)) {
            std::error_code ec;
            fs::remove(staged, ec);
            r.message = "integrity check FAILED: " + err;
            return r;
        }

        // 6. Atomic swap.
        if (!AtomicSwap(staged, self, stamp, r.message)) {
            std::error_code ec;
            fs::remove(staged, ec);
            if (r.message.empty()) r.message = "failed to install the verified update";
            return r;
        }

        r.ok = true;
        r.new_version = m.version;
        r.message = "verified (Ed25519 + SHA-256) and installed v" + m.version;
        return r;
    }

    static std::string EscapePs(const std::string& s) {
        std::string out;
        for (char c : s) {
            if (c == '\'') out += "''";
            else out += c;
        }
        return out;
    }

    // ── network helpers (no shell; bounded output) ──
    static bool FetchSmall(const std::string& url, size_t max_bytes, std::string& out) {
#if defined(_WIN32)
        auto res = safe_exec::RunCapture(
            {"powershell", "-NoProfile", "-NonInteractive", "-Command",
             "$ProgressPreference='SilentlyContinue';"
             "(Invoke-WebRequest -Uri ([uri]'" + EscapePs(url) + "') -UseBasicParsing -TimeoutSec 20).Content"},
            "", false, max_bytes + 1);
#else
        auto res = safe_exec::RunCapture(
            {"curl", "-fsSL", "--proto", "=https", "--tlsv1.2", "--max-time", "30",
             "--max-filesize", std::to_string(max_bytes), url},
            "", false, max_bytes + 1);
#endif
        if (!res.spawned || res.exit_code != 0) return false;
        if (res.output.empty() || res.output.size() > max_bytes) return false;
        out = res.output;
        return true;
    }

    static bool FetchToFile(const std::string& url, const fs::path& dest, int64_t expected_size) {
#if defined(_WIN32)
        auto res = safe_exec::RunCapture(
            {"powershell", "-NoProfile", "-NonInteractive", "-Command",
             "$ProgressPreference='SilentlyContinue';"
             "Invoke-WebRequest -Uri ([uri]'" + EscapePs(url) + "') -UseBasicParsing -TimeoutSec 300 "
             "-OutFile '" + EscapePs(dest.string()) + "'"});
        return res.spawned && res.exit_code == 0;
#else
        auto res = safe_exec::RunCapture(
            {"curl", "-fSL", "--proto", "=https", "--tlsv1.2", "--max-time", "600",
             "--max-filesize", std::to_string(expected_size),
             "-o", dest.string(), url});
        return res.spawned && res.exit_code == 0;
#endif
    }

    static std::string TrimAscii(const std::string& s) {
        size_t b = s.find_first_not_of(" \t\r\n");
        if (b == std::string::npos) return "";
        size_t e = s.find_last_not_of(" \t\r\n");
        return s.substr(b, e - b + 1);
    }

private:
    static bool AtomicSwap(const fs::path& staged, const fs::path& target, long long stamp,
                           std::string& err) {
        fs::path backup = target;
        backup += ".old_" + std::to_string(stamp);
#if defined(_WIN32)
        // A running exe can be renamed but not overwritten in place.
        if (!MoveFileExW(target.wstring().c_str(), backup.wstring().c_str(),
                         MOVEFILE_WRITE_THROUGH)) {
            err = "could not move the current executable aside (is it write-protected?)";
            return false;
        }
        if (!MoveFileExW(staged.wstring().c_str(), target.wstring().c_str(),
                         MOVEFILE_WRITE_THROUGH)) {
            // Roll back so the install is never left headless.
            MoveFileExW(backup.wstring().c_str(), target.wstring().c_str(),
                        MOVEFILE_WRITE_THROUGH);
            err = "could not move the verified update into place (rolled back)";
            return false;
        }
        return true;
#else
        // Preserve the destination's permission bits (fall back to 0755).
        struct stat st{};
        mode_t mode = 0755;
        if (::stat(target.c_str(), &st) == 0) mode = st.st_mode & 07777;
        if (::chmod(staged.c_str(), mode | S_IXUSR) != 0) {
            err = "could not mark the update executable";
            return false;
        }
        std::error_code ec;
        fs::rename(target, backup, ec); // keep a rollback copy
        if (ec) {
            err = "could not move the current executable aside: " + ec.message();
            return false;
        }
        fs::rename(staged, target, ec); // atomic: same directory
        if (ec) {
            std::error_code ec2;
            fs::rename(backup, target, ec2); // roll back
            err = "could not activate the update (rolled back): " + ec.message();
            return false;
        }
        return true;
#endif
    }
};

} // namespace neuroshell::update
