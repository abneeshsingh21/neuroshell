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
    static void EnsureDaemonRunningAsync(NeuroShell::IPC::NeuroIPCClient& ipc) {
        // Fast instant check
        if (ipc.Ping()) return;

        // Prevent duplicate background spawn threads
        if (is_spawning_.exchange(true)) {
            return;
        }

        // Spawn background Python daemon without blocking the UI main thread
        std::thread([&ipc]() {
#if defined(_WIN32)
            // Ensure single instance daemon on Windows via Named Mutex
            HANDLE hDaemonMutex = CreateMutexW(NULL, TRUE, L"Local\\NeuroShell_Python_Daemon_Mutex");
            if (GetLastError() == ERROR_ALREADY_EXISTS) {
                if (hDaemonMutex) CloseHandle(hDaemonMutex);
                is_spawning_.store(false);
                return;
            }

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
            }
#else
            // Double-fork daemonization: the intermediate child exits
            // immediately and is reaped here, so the grandchild is adopted by
            // init/systemd. The previous single fork left a permanent zombie
            // because the host never called waitpid().
            pid_t pid = fork();
            if (pid == 0) {
                setsid();
                pid_t pid2 = fork();
                if (pid2 != 0) _exit(0); // intermediate exits at once

                int devNull = open("/dev/null", O_RDWR);
                if (devNull >= 0) {
                    dup2(devNull, STDIN_FILENO);
                    dup2(devNull, STDOUT_FILENO);
                    dup2(devNull, STDERR_FILENO);
                    close(devNull);
                }
                execlp("python3", "python3", "-m", "core.ipc_server", (char*)NULL);
                execlp("python", "python", "-m", "core.ipc_server", (char*)NULL);
                _exit(1);
            } else if (pid > 0) {
                int status = 0;
                waitpid(pid, &status, 0); // reap the intermediate immediately
            }
#endif
            // Background polling loop (runs off the main thread)
            for (int i = 0; i < 20; ++i) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                if (ipc.Ping()) break;
            }
            is_spawning_.store(false);
        }).detach();
    }
};

} // namespace NeuroShell::Daemon
