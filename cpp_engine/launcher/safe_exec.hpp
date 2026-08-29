// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// SafeExec — injection-proof subprocess primitives for the native host.
//
// Historically the host built shell command lines by string concatenation and
// passed them to system()/popen(). Any user-controlled token (repo names, URLs,
// secrets, SSIDs) could break out of quoting and execute arbitrary commands.
//
// This header provides:
//   * RunCapture(argv)      — fork/exec (posix_spawn-style) with NO shell, captures stdout
//   * RunStatus(argv)       — same, returns exit status only
//   * QuotePosix()/QuoteWin()— last-resort strict quoting when a shell is unavoidable
//   * Validators             — allowlist checks for repo slugs, hosts, filenames
#pragma once

#include <string>
#include <vector>
#include <cctype>
#include <cstring>

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <unistd.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <signal.h>
#endif

namespace neuroshell::safe_exec {

// ─────────────────────────────────────────────────────────────
// Input validators (allowlist > blocklist)
// ─────────────────────────────────────────────────────────────

// GitHub "owner/repo" slug: alnum, '-', '_', '.', exactly one '/'
inline bool IsValidRepoSlug(const std::string& s) {
    if (s.empty() || s.size() > 140) return false;
    int slashes = 0;
    for (char c : s) {
        if (c == '/') { ++slashes; continue; }
        if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '-' || c == '_' || c == '.')) {
            return false;
        }
    }
    if (slashes != 1) return false;
    if (s.front() == '/' || s.back() == '/') return false;
    if (s.find("..") != std::string::npos) return false;
    return true;
}

// GitHub username / org
inline bool IsValidGitHubUser(const std::string& s) {
    if (s.empty() || s.size() > 39) return false;
    for (char c : s) {
        if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '-')) return false;
    }
    return s.front() != '-' && s.back() != '-';
}

// Hostname / IP for ping-style commands
inline bool IsValidHost(const std::string& s) {
    if (s.empty() || s.size() > 253) return false;
    for (char c : s) {
        if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '-' || c == '.' || c == ':')) {
            return false;
        }
    }
    return true;
}

// Secret-vault key names ("groq_api_key", ...)
inline bool IsValidVaultKey(const std::string& s) {
    if (s.empty() || s.size() > 64) return false;
    for (char c : s) {
        if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '-' || c == '_' || c == '.')) {
            return false;
        }
    }
    return true;
}

// ─────────────────────────────────────────────────────────────
// Strict shell quoting (only for cases where a shell is required)
// ─────────────────────────────────────────────────────────────

inline std::string QuotePosix(const std::string& arg) {
    // Wrap in single quotes; embedded single quotes become '\''
    std::string out = "'";
    for (char c : arg) {
        if (c == '\'') out += "'\\''";
        else out += c;
    }
    out += "'";
    return out;
}

inline std::string QuoteWin(const std::string& arg) {
    // Standard MSVC CommandLineToArgvW-compatible quoting
    if (!arg.empty() && arg.find_first_of(" \t\"^&|<>()%!") == std::string::npos) return arg;
    std::string out = "\"";
    size_t backslashes = 0;
    for (char c : arg) {
        if (c == '\\') { ++backslashes; continue; }
        if (c == '"') {
            out.append(backslashes * 2 + 1, '\\');
            out += '"';
            backslashes = 0;
            continue;
        }
        out.append(backslashes, '\\');
        backslashes = 0;
        out += c;
    }
    out.append(backslashes * 2, '\\');
    out += "\"";
    return out;
}

struct ExecCaptureResult {
    int exit_code = -1;
    bool spawned = false;
    std::string output;   // combined stdout (stderr suppressed unless merge_stderr)
};

// ─────────────────────────────────────────────────────────────
// No-shell argv execution with stdout capture
// ─────────────────────────────────────────────────────────────
inline ExecCaptureResult RunCapture(const std::vector<std::string>& argv,
                                    const std::string& stdin_data = "",
                                    bool merge_stderr = false,
                                    size_t max_output = 4 * 1024 * 1024) {
    ExecCaptureResult res;
    if (argv.empty()) return res;

#if defined(_WIN32)
    // Build a properly-quoted command line (CreateProcess has no argv API,
    // but per-argument quoting is injection-safe).
    std::string cmdline;
    for (size_t i = 0; i < argv.size(); ++i) {
        if (i) cmdline += ' ';
        cmdline += QuoteWin(argv[i]);
    }

    SECURITY_ATTRIBUTES sa{ sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE };
    HANDLE outR = nullptr, outW = nullptr, inR = nullptr, inW = nullptr;
    if (!CreatePipe(&outR, &outW, &sa, 0)) return res;
    SetHandleInformation(outR, HANDLE_FLAG_INHERIT, 0);
    if (!stdin_data.empty()) {
        if (!CreatePipe(&inR, &inW, &sa, 0)) { CloseHandle(outR); CloseHandle(outW); return res; }
        SetHandleInformation(inW, HANDLE_FLAG_INHERIT, 0);
    }

    STARTUPINFOA si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = outW;
    si.hStdError = merge_stderr ? outW : GetStdHandle(STD_ERROR_HANDLE);
    si.hStdInput = inR ? inR : GetStdHandle(STD_INPUT_HANDLE);

    PROCESS_INFORMATION pi{};
    std::vector<char> buf(cmdline.begin(), cmdline.end());
    buf.push_back('\0');

    BOOL ok = CreateProcessA(nullptr, buf.data(), nullptr, nullptr, TRUE,
                             CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
    CloseHandle(outW);
    if (inR) CloseHandle(inR);

    if (!ok) {
        CloseHandle(outR);
        if (inW) CloseHandle(inW);
        return res;
    }
    res.spawned = true;

    if (inW) {
        DWORD written = 0;
        WriteFile(inW, stdin_data.data(), (DWORD)stdin_data.size(), &written, nullptr);
        CloseHandle(inW);
    }

    char chunk[4096];
    DWORD n = 0;
    while (ReadFile(outR, chunk, sizeof(chunk), &n, nullptr) && n > 0) {
        if (res.output.size() < max_output) res.output.append(chunk, n);
    }
    CloseHandle(outR);

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    res.exit_code = static_cast<int>(code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
#else
    int outPipe[2] = { -1, -1 };
    int inPipe[2]  = { -1, -1 };
    if (pipe(outPipe) != 0) return res;
    if (!stdin_data.empty() && pipe(inPipe) != 0) {
        close(outPipe[0]); close(outPipe[1]);
        return res;
    }

    pid_t pid = fork();
    if (pid < 0) {
        close(outPipe[0]); close(outPipe[1]);
        if (inPipe[0] >= 0) { close(inPipe[0]); close(inPipe[1]); }
        return res;
    }

    if (pid == 0) {
        // Child: no shell involved — direct execvp of argv[0]
        close(outPipe[0]);
        dup2(outPipe[1], STDOUT_FILENO);
        if (merge_stderr) dup2(outPipe[1], STDERR_FILENO);
        else {
            int devnull = open("/dev/null", O_WRONLY);
            if (devnull >= 0) { dup2(devnull, STDERR_FILENO); close(devnull); }
        }
        close(outPipe[1]);

        if (inPipe[0] >= 0) {
            close(inPipe[1]);
            dup2(inPipe[0], STDIN_FILENO);
            close(inPipe[0]);
        } else {
            int devnull = open("/dev/null", O_RDONLY);
            if (devnull >= 0) { dup2(devnull, STDIN_FILENO); close(devnull); }
        }

        std::vector<char*> cargv;
        cargv.reserve(argv.size() + 1);
        for (const auto& a : argv) cargv.push_back(const_cast<char*>(a.c_str()));
        cargv.push_back(nullptr);
        execvp(cargv[0], cargv.data());
        _exit(127);
    }

    close(outPipe[1]);
    res.spawned = true;

    if (inPipe[0] >= 0) {
        close(inPipe[0]);
        // Best-effort write; ignore SIGPIPE via MSG-less write guard
        ssize_t off = 0;
        const char* p = stdin_data.data();
        ssize_t total = (ssize_t)stdin_data.size();
        while (off < total) {
            ssize_t w = write(inPipe[1], p + off, (size_t)(total - off));
            if (w <= 0) break;
            off += w;
        }
        close(inPipe[1]);
    }

    char chunk[4096];
    ssize_t n = 0;
    while ((n = read(outPipe[0], chunk, sizeof(chunk))) > 0) {
        if (res.output.size() < max_output) res.output.append(chunk, (size_t)n);
    }
    close(outPipe[0]);

    int status = 0;
    if (waitpid(pid, &status, 0) == pid) {
        if (WIFEXITED(status)) res.exit_code = WEXITSTATUS(status);
        else if (WIFSIGNALED(status)) res.exit_code = 128 + WTERMSIG(status);
        else res.exit_code = 1;
    }
#endif
    return res;
}

inline int RunStatus(const std::vector<std::string>& argv, const std::string& stdin_data = "") {
    return RunCapture(argv, stdin_data, /*merge_stderr=*/false, /*max_output=*/64 * 1024).exit_code;
}

// Trim helper shared by callers
inline std::string Trim(const std::string& s) {
    size_t b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos) return "";
    size_t e = s.find_last_not_of(" \t\r\n");
    return s.substr(b, e - b + 1);
}

} // namespace neuroshell::safe_exec
