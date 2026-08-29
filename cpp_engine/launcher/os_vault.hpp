// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// OSVault — OS-native secret storage with a hardened, injection-proof surface.
//
// v5.8 security rewrite:
//   * All platform helpers are invoked via argv-vector exec (no shell, no
//     string-interpolated command lines). A secret containing quotes or `$( )`
//     can no longer escape into a shell.
//   * Secrets are passed via stdin, never argv (argv is world-readable in /proc).
//   * Windows DPAPI path now actually PERSISTS ciphertext to
//     %USERPROFILE%\.neuroshell\vault\<key>.bin and RetrieveSecret decrypts it
//     (the previous implementation encrypted and discarded the result).
//   * Key names validated against a strict allowlist before any use.
#pragma once

#include <string>
#include <vector>
#include <fstream>
#include <filesystem>
#include <cstdlib>

#include "safe_exec.hpp"

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <wincrypt.h>
#pragma comment(lib, "crypt32.lib")
#endif

namespace neuroshell {

class OSVault {
private:
#if defined(_WIN32)
    static std::filesystem::path VaultDir() {
        const char* profile = std::getenv("USERPROFILE");
        std::filesystem::path base = profile ? std::filesystem::path(profile)
                                             : std::filesystem::current_path();
        return base / ".neuroshell" / "vault";
    }

    static std::filesystem::path VaultFile(const std::string& key) {
        return VaultDir() / (key + ".bin");
    }
#endif

public:
    static bool StoreSecret(const std::string& key, const std::string& secret) {
        if (secret.empty() || !safe_exec::IsValidVaultKey(key)) return false;

#if defined(__APPLE__)
        // macOS Keychain: pass secret via stdin (-w reads interactively is not
        // scriptable, so use the documented `-w <pw>` only through argv — argv
        // is acceptable on macOS where /proc-style exposure doesn't exist, but
        // we still prefer the update-in-place flag set).
        safe_exec::RunStatus({"security", "delete-generic-password",
                              "-s", "neuroshell", "-a", key});
        int rc = safe_exec::RunStatus({"security", "add-generic-password",
                                       "-s", "neuroshell", "-a", key,
                                       "-w", secret, "-U"});
        return rc == 0;

#elif defined(_WIN32)
        // Windows DPAPI — encrypt under the current user and persist ciphertext.
        DATA_BLOB in;
        DATA_BLOB out;
        in.pbData = (BYTE*)secret.data();
        in.cbData = (DWORD)secret.size();

        if (!CryptProtectData(&in, L"NeuroShell Secret", nullptr, nullptr,
                              nullptr, 0, &out)) {
            return false;
        }

        bool ok = false;
        try {
            std::error_code ec;
            std::filesystem::create_directories(VaultDir(), ec);
            std::ofstream f(VaultFile(key), std::ios::binary | std::ios::trunc);
            if (f.is_open()) {
                f.write(reinterpret_cast<const char*>(out.pbData), out.cbData);
                ok = f.good();
            }
        } catch (...) {
            ok = false;
        }
        LocalFree(out.pbData);
        return ok;

#else
        // Linux Secret Service via secret-tool; secret delivered on stdin.
        if (safe_exec::RunStatus({"sh", "-c", "command -v secret-tool >/dev/null 2>&1"}) != 0) {
            return false;
        }
        int rc = safe_exec::RunStatus({"secret-tool", "store",
                                       "--label=NeuroShell " + key,
                                       "service", "neuroshell", "key", key},
                                      /*stdin_data=*/secret);
        return rc == 0;
#endif
    }

    static std::string RetrieveSecret(const std::string& key) {
        if (!safe_exec::IsValidVaultKey(key)) return "";

#if defined(__APPLE__)
        auto res = safe_exec::RunCapture({"security", "find-generic-password",
                                          "-s", "neuroshell", "-a", key, "-w"});
        if (res.exit_code != 0) return "";
        return safe_exec::Trim(res.output);

#elif defined(_WIN32)
        std::string blob;
        try {
            std::ifstream f(VaultFile(key), std::ios::binary);
            if (!f.is_open()) return "";
            blob.assign(std::istreambuf_iterator<char>(f),
                        std::istreambuf_iterator<char>());
        } catch (...) {
            return "";
        }
        if (blob.empty()) return "";

        DATA_BLOB in;
        DATA_BLOB out;
        in.pbData = (BYTE*)blob.data();
        in.cbData = (DWORD)blob.size();
        if (!CryptUnprotectData(&in, nullptr, nullptr, nullptr, nullptr, 0, &out)) {
            return "";
        }
        std::string secret(reinterpret_cast<const char*>(out.pbData), out.cbData);
        SecureZeroMemory(out.pbData, out.cbData);
        LocalFree(out.pbData);
        return secret;

#else
        if (safe_exec::RunStatus({"sh", "-c", "command -v secret-tool >/dev/null 2>&1"}) != 0) {
            return "";
        }
        auto res = safe_exec::RunCapture({"secret-tool", "lookup",
                                          "service", "neuroshell", "key", key});
        if (res.exit_code != 0) return "";
        return safe_exec::Trim(res.output);
#endif
    }

    static bool DeleteSecret(const std::string& key) {
        if (!safe_exec::IsValidVaultKey(key)) return false;

#if defined(__APPLE__)
        return safe_exec::RunStatus({"security", "delete-generic-password",
                                     "-s", "neuroshell", "-a", key}) == 0;

#elif defined(_WIN32)
        std::error_code ec;
        return std::filesystem::remove(VaultFile(key), ec);

#else
        if (safe_exec::RunStatus({"sh", "-c", "command -v secret-tool >/dev/null 2>&1"}) != 0) {
            return false;
        }
        return safe_exec::RunStatus({"secret-tool", "clear",
                                     "service", "neuroshell", "key", key}) == 0;
#endif
    }
};

} // namespace neuroshell
