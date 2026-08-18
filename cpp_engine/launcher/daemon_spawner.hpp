#pragma once
// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Proprietary and Confidential - see LICENSE.txt

#include <iostream>
#include <string>
#include <vector>
#include <thread>
#include <chrono>
#include "ipc_client.hpp"

#if defined(_WIN32)
    #define WIN32_LEAN_AND_MEAN
    #include <windows.h>
#else
    #include <unistd.h>
    #include <fcntl.h>
    #include <sys/types.h>
#endif

namespace NeuroShell::Daemon {

class DaemonManager {
public:
    static bool EnsureDaemonRunning(NeuroShell::IPC::NeuroIPCClient& ipc) {
        if (ipc.Ping()) {
            return true;
        }

        std::cout << "\033[38;2;100;116;139m  ⚡ Connecting to NeuroShell Intelligence Daemon...\033[0m\r" << std::flush;

#if defined(_WIN32)
        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        si.cb = sizeof(si);
        si.dwFlags |= STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;

        std::wstring cmd = L"python -m core.ipc_server";
        std::vector<wchar_t> cmdBuf(cmd.begin(), cmd.end());
        cmdBuf.push_back(0);

        BOOL success = CreateProcessW(
            NULL, cmdBuf.data(), NULL, NULL, FALSE,
            CREATE_NO_WINDOW | DETACHED_PROCESS, NULL, NULL, &si, &pi
        );
        if (success) {
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
        }
#else
        pid_t pid = fork();
        if (pid == 0) {
            setsid();
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
        }
#endif

        // Poll for up to 1.5 seconds
        for (int i = 0; i < 15; ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            if (ipc.Ping()) {
                std::cout << "\033[2K\r" << std::flush;
                return true;
            }
        }
        std::cout << "\033[2K\r" << std::flush;
        return false;
    }
};

} // namespace NeuroShell::Daemon
