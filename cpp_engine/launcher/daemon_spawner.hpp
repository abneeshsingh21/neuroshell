#pragma once
// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Proprietary and Confidential - see LICENSE.txt

#include <iostream>
#include <string>
#include <vector>
#include <thread>
#include <chrono>
#include <atomic>
#include <filesystem>
#include "ipc_client.hpp"

#if defined(_WIN32)
    #define WIN32_LEAN_AND_MEAN
    #include <windows.h>
#else
    #include <unistd.h>
    #include <fcntl.h>
    #include <sys/types.h>
    #include <sys/wait.h>
#endif

namespace NeuroShell::Daemon {

class DaemonManager {
private:
    static inline std::atomic<bool> is_spawning_{false};

public:
private:
    static bool SpawnProcess() {
#if defined(_WIN32)
        std::wstring appDir;
        wchar_t exeBuf[MAX_PATH * 2];
        DWORD n = GetModuleFileNameW(nullptr, exeBuf, MAX_PATH * 2);
        if (n > 0) {
            std::filesystem::path p(exeBuf);
            if (std::filesystem::exists(p.parent_path() / "core")) {
                appDir = p.parent_path().wstring();
            } else if (std::filesystem::exists(p.parent_path().parent_path() / "core")) {
                appDir = p.parent_path().parent_path().wstring();
            } else {
                appDir = p.parent_path().wstring();
            }
        }

        std::wstring pythonExe = L"python";
        if (!appDir.empty()) {
            std::filesystem::path venvPy = std::filesystem::path(appDir) / ".venv" / "Scripts" / "python.exe";
            if (std::filesystem::exists(venvPy)) {
                pythonExe = L"\"" + venvPy.wstring() + L"\"";
            }
        }

        std::wstring cmd = pythonExe + L" -m core.ipc_server";
        std::vector<wchar_t> cmdBuf(cmd.begin(), cmd.end());
        cmdBuf.push_back(0);

        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        si.cb = sizeof(si);
        si.dwFlags |= STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;

        BOOL success = CreateProcessW(
            NULL, cmdBuf.data(), NULL, NULL, FALSE,
            CREATE_NO_WINDOW | DETACHED_PROCESS, NULL,
            appDir.empty() ? NULL : appDir.c_str(),
            &si, &pi
        );
        if (success) {
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
            return true;
        }
        return false;
#else
        pid_t pid = fork();
        if (pid == 0) {
            setsid();
            pid_t pid2 = fork();
            if (pid2 != 0) _exit(0);

            int devNull = open("/dev/null", O_RDWR);
            if (devNull >= 0) {
                dup2(devNull, STDIN_FILENO);
                dup2(devNull, STDOUT_FILENO);
                dup2(devNull, STDERR_FILENO);
                close(devNull);
            }
            execlp("python3", "python3", "-m", "core.ipc_server", (char*)nullptr);
            _exit(1);
        }
        if (pid > 0) waitpid(pid, nullptr, 0);
        return true;
#endif
    }

public:
    static bool EnsureDaemonRunningSync(NeuroShell::IPC::NeuroIPCClient& ipc, int timeoutSeconds = 20) {
        if (ipc.Ping()) return true;

        SpawnProcess();

        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(timeoutSeconds);
        while (std::chrono::steady_clock::now() < deadline) {
            std::this_thread::sleep_for(std::chrono::milliseconds(150));
            if (ipc.Ping()) return true;
        }
        return ipc.Ping();
    }

    static void EnsureDaemonRunningAsync(NeuroShell::IPC::NeuroIPCClient& ipc) {
        if (ipc.Ping()) return;

        if (is_spawning_.exchange(true)) {
            return;
        }

        std::thread([&ipc]() {
            EnsureDaemonRunningSync(ipc, 20);
            is_spawning_.store(false);
        }).detach();
    }
};

} // namespace NeuroShell::Daemon
