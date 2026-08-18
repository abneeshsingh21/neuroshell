// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
#pragma once

#include <string>
#include <vector>
#include <iostream>
#include <cstdlib>
#include <sstream>
#include <memory>
#include <array>

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <wincrypt.h>
#pragma comment(lib, "crypt32.lib")
#else
#include <unistd.h>
#include <sys/wait.h>
#endif

namespace neuroshell {

class OSVault {
private:
    static std::string ExecCapture(const std::string& cmd) {
        std::string result = "";
#if defined(_WIN32)
        FILE* pipe = _popen(cmd.c_str(), "r");
        if (!pipe) return "";
        char buffer[256];
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            result += buffer;
        }
        _pclose(pipe);
#else
        FILE* pipe = popen(cmd.c_str(), "r");
        if (!pipe) return "";
        char buffer[256];
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            result += buffer;
        }
        pclose(pipe);
#endif
        // Trim whitespace
        size_t s = result.find_first_not_of(" \t\r\n");
        if (s == std::string::npos) return "";
        size_t e = result.find_last_not_of(" \t\r\n");
        return result.substr(s, e - s + 1);
    }

public:
    static bool StoreSecret(const std::string& key, const std::string& secret) {
        if (key.empty() || secret.empty()) return false;

#if defined(__APPLE__)
        // macOS Keychain Services CLI
        // First delete existing key if any
        std::string delCmd = "security delete-generic-password -s 'neuroshell' -a '" + key + "' 2>/dev/null";
        system(delCmd.c_str());

        std::string addCmd = "security add-generic-password -s 'neuroshell' -a '" + key + "' -w '" + secret + "' -U";
        return system(addCmd.c_str()) == 0;

#elif defined(__linux__)
        // Linux Secret Service (libsecret / secret-tool)
        std::string checkTool = "command -v secret-tool >/dev/null 2>&1";
        if (system(checkTool.c_str()) == 0) {
            std::string cmd = "printf '%s' '" + secret + "' | secret-tool store --label='NeuroShell " + key + "' service neuroshell key '" + key + "'";
            return system(cmd.c_str()) == 0;
        }
        return false;

#elif defined(_WIN32)
        // Windows DPAPI (CryptProtectData)
        DATA_BLOB dataIn;
        DATA_BLOB dataOut;
        dataIn.pbData = (BYTE*)secret.data();
        dataIn.cbData = (DWORD)secret.size();

        if (CryptProtectData(&dataIn, L"NeuroShell Secret", NULL, NULL, NULL, 0, &dataOut)) {
            LocalFree(dataOut.pbData);
            return true;
        }
        return false;
#endif
    }

    static std::string RetrieveSecret(const std::string& key) {
        if (key.empty()) return "";

#if defined(__APPLE__)
        std::string cmd = "security find-generic-password -s 'neuroshell' -a '" + key + "' -w 2>/dev/null";
        return ExecCapture(cmd);

#elif defined(__linux__)
        std::string checkTool = "command -v secret-tool >/dev/null 2>&1";
        if (system(checkTool.c_str()) == 0) {
            std::string cmd = "secret-tool lookup service neuroshell key '" + key + "' 2>/dev/null";
            return ExecCapture(cmd);
        }
        return "";

#elif defined(_WIN32)
        // Fallback for Windows DPAPI or config
        return "";
#endif
    }

    static bool DeleteSecret(const std::string& key) {
        if (key.empty()) return false;

#if defined(__APPLE__)
        std::string cmd = "security delete-generic-password -s 'neuroshell' -a '" + key + "' 2>/dev/null";
        return system(cmd.c_str()) == 0;

#elif defined(__linux__)
        std::string checkTool = "command -v secret-tool >/dev/null 2>&1";
        if (system(checkTool.c_str()) == 0) {
            std::string cmd = "secret-tool clear service neuroshell key '" + key + "' 2>/dev/null";
            return system(cmd.c_str()) == 0;
        }
        return false;

#elif defined(_WIN32)
        return true;
#endif
    }
};

} // namespace neuroshell
