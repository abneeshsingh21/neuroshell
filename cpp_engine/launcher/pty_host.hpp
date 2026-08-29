#pragma once
// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Proprietary and Confidential - see LICENSE.txt

#include <iostream>
#include <string>
#include <vector>
#include <functional>
#include <atomic>
#include <thread>

#if !defined(_WIN32)
    #include <poll.h>
#endif

#if defined(_WIN32)
    #define WIN32_LEAN_AND_MEAN
    #include <windows.h>
    #include <process.h>
#else
    #include <termios.h>
    #include <unistd.h>
    #include <sys/ioctl.h>
    #include <sys/wait.h>
    #include <sys/types.h>
    #if defined(__APPLE__)
        #include <util.h>
    #elif defined(__linux__)
        #include <pty.h>
    #endif
#endif

namespace NeuroShell::PTY {

class PseudoTerminalHost {
private:
#if defined(_WIN32)
    HPCON hPC = INVALID_HANDLE_VALUE;
    HANDLE hPipeInRead = INVALID_HANDLE_VALUE;
    HANDLE hPipeInWrite = INVALID_HANDLE_VALUE;
    HANDLE hPipeOutRead = INVALID_HANDLE_VALUE;
    HANDLE hPipeOutWrite = INVALID_HANDLE_VALUE;
    PROCESS_INFORMATION pi = { 0 };
#else
    int masterFd = -1;
    pid_t childPid = -1;
#endif
    std::atomic<bool> isRunning{ false };

public:
    PseudoTerminalHost() = default;
    ~PseudoTerminalHost() { Cleanup(); }

    bool Spawn(const std::string& command, short cols, short rows) {
#if defined(_WIN32)
        // 1. Create I/O Pipes
        if (!CreatePipe(&hPipeInRead, &hPipeInWrite, NULL, 0)) return false;
        if (!CreatePipe(&hPipeOutRead, &hPipeOutWrite, NULL, 0)) {
            CloseHandle(hPipeInRead);
            CloseHandle(hPipeInWrite);
            return false;
        }

        // 2. Initialize Windows ConPTY
        COORD size = { cols, rows };
        HRESULT hr = CreatePseudoConsole(size, hPipeInRead, hPipeOutWrite, 0, &hPC);
        if (FAILED(hr)) {
            CloseHandle(hPipeInRead);
            CloseHandle(hPipeInWrite);
            CloseHandle(hPipeOutRead);
            CloseHandle(hPipeOutWrite);
            return false;
        }

        // Clean parent copies of child handles
        CloseHandle(hPipeInRead);
        CloseHandle(hPipeOutWrite);

        // 3. Configure Extended Process Startup Info
        SIZE_T bytesRequired = 0;
        InitializeProcThreadAttributeList(NULL, 1, 0, &bytesRequired);
        std::vector<BYTE> attrList(bytesRequired);
        PPROC_THREAD_ATTRIBUTE_LIST pAttrList = reinterpret_cast<PPROC_THREAD_ATTRIBUTE_LIST>(attrList.data());
        if (!InitializeProcThreadAttributeList(pAttrList, 1, 0, &bytesRequired)) {
            ClosePseudoConsole(hPC);
            return false;
        }

        if (!UpdateProcThreadAttribute(
                pAttrList, 0,
                PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                hPC, sizeof(HPCON), NULL, NULL)) {
            DeleteProcThreadAttributeList(pAttrList);
            ClosePseudoConsole(hPC);
            return false;
        }

        STARTUPINFOEXW siex = { 0 };
        siex.StartupInfo.cb = sizeof(STARTUPINFOEXW);
        siex.lpAttributeList = pAttrList;

        std::wstring wCmd = L"cmd.exe /c " + std::wstring(command.begin(), command.end());
        std::vector<wchar_t> cmdBuf(wCmd.begin(), wCmd.end());
        cmdBuf.push_back(0);

        BOOL success = CreateProcessW(
            NULL, cmdBuf.data(), NULL, NULL, FALSE,
            EXTENDED_STARTUPINFO_PRESENT,
            NULL, NULL, &siex.StartupInfo, &pi
        );

        DeleteProcThreadAttributeList(pAttrList);

        if (!success) {
            ClosePseudoConsole(hPC);
            return false;
        }

        isRunning = true;
        return true;
#else
        struct winsize ws = { (unsigned short)rows, (unsigned short)cols, 0, 0 };
        childPid = forkpty(&masterFd, NULL, NULL, &ws);

        if (childPid < 0) return false;

        if (childPid == 0) {
            const char* shell = getenv("SHELL");
            if (!shell) shell = "/bin/bash";
            execlp(shell, shell, "-c", command.c_str(), (char*)NULL);
            _exit(127);
        }

        isRunning = true;
        return true;
#endif
    }

    void Resize(short cols, short rows) {
#if defined(_WIN32)
        if (hPC != INVALID_HANDLE_VALUE) {
            COORD size = { cols, rows };
            ResizePseudoConsole(hPC, size);
        }
#else
        if (masterFd >= 0) {
            struct winsize ws = { (unsigned short)rows, (unsigned short)cols, 0, 0 };
            ioctl(masterFd, TIOCSWINSZ, &ws);
        }
#endif
    }

    bool IsActive() const { return isRunning.load(); }

    void WriteInput(const char* data, size_t len) {
#if defined(_WIN32)
        if (hPipeInWrite != INVALID_HANDLE_VALUE) {
            DWORD written = 0;
            WriteFile(hPipeInWrite, data, (DWORD)len, &written, NULL);
        }
#else
        if (masterFd >= 0) {
            size_t off = 0;
            while (off < len) {
                ssize_t n = write(masterFd, data + off, len - off);
                if (n <= 0) break; // child gone / EIO — stop forwarding
                off += (size_t)n;
            }
        }
#endif
    }

    void WriteInput(const std::string& data) {
        WriteInput(data.data(), data.size());
    }

    void StreamOutput(std::function<void(const char*, size_t)> onData) {
        char buffer[8192];
#if defined(_WIN32)
        DWORD bytesRead = 0;
        while (ReadFile(hPipeOutRead, buffer, sizeof(buffer), &bytesRead, NULL) && bytesRead > 0) {
            onData(buffer, bytesRead);
        }
#else
        ssize_t n = 0;
        while ((n = read(masterFd, buffer, sizeof(buffer))) > 0) {
            onData(buffer, (size_t)n);
        }
#endif
    }

    // Forward local stdin keystrokes into the child PTY until the child exits.
    // Without this pump, full-screen apps (vim, htop, ssh) rendered but never
    // received input — the terminal appeared frozen.
    void PumpStdinLoop() {
#if defined(_WIN32)
        HANDLE hStdin = GetStdHandle(STD_INPUT_HANDLE);
        if (hStdin == INVALID_HANDLE_VALUE) return;
        char buf[512];
        while (isRunning.load()) {
            DWORD waitRes = WaitForSingleObject(hStdin, 50);
            if (waitRes != WAIT_OBJECT_0) continue;

            INPUT_RECORD records[64];
            DWORD count = 0;
            if (!PeekConsoleInputA(hStdin, records, 64, &count) || count == 0) continue;

            DWORD readCount = 0;
            if (!ReadConsoleInputA(hStdin, records, 64, &readCount)) break;

            size_t len = 0;
            for (DWORD i = 0; i < readCount && len < sizeof(buf); ++i) {
                if (records[i].EventType == KEY_EVENT &&
                    records[i].Event.KeyEvent.bKeyDown &&
                    records[i].Event.KeyEvent.uChar.AsciiChar != 0) {
                    buf[len++] = records[i].Event.KeyEvent.uChar.AsciiChar;
                }
            }
            if (len > 0) WriteInput(buf, len);
        }
#else
        char buf[512];
        while (isRunning.load()) {
            struct pollfd pfd = { STDIN_FILENO, POLLIN, 0 };
            int pr = poll(&pfd, 1, 50);
            if (pr <= 0) continue;
            ssize_t n = read(STDIN_FILENO, buf, sizeof(buf));
            if (n <= 0) break;
            WriteInput(buf, (size_t)n);
        }
#endif
    }

    int WaitForExit() {
        int exitCode = 0;
#if defined(_WIN32)
        if (pi.hProcess != INVALID_HANDLE_VALUE && pi.hProcess != NULL) {
            WaitForSingleObject(pi.hProcess, INFINITE);
            DWORD dwCode = 0;
            GetExitCodeProcess(pi.hProcess, &dwCode);
            exitCode = (int)dwCode;
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
            pi.hProcess = NULL;
            pi.hThread = NULL;
        }
#else
        if (childPid > 0) {
            int status = 0;
            waitpid(childPid, &status, 0);
            if (WIFEXITED(status)) exitCode = WEXITSTATUS(status);
            else if (WIFSIGNALED(status)) exitCode = 128 + WTERMSIG(status);
            else exitCode = 1;
            childPid = -1;
        }
#endif
        Cleanup();
        return exitCode;
    }

    void Cleanup() {
        isRunning = false;
#if defined(_WIN32)
        if (hPipeInWrite != INVALID_HANDLE_VALUE) { CloseHandle(hPipeInWrite); hPipeInWrite = INVALID_HANDLE_VALUE; }
        if (hPipeOutRead != INVALID_HANDLE_VALUE) { CloseHandle(hPipeOutRead); hPipeOutRead = INVALID_HANDLE_VALUE; }
        if (hPC != INVALID_HANDLE_VALUE) { ClosePseudoConsole(hPC); hPC = INVALID_HANDLE_VALUE; }
#else
        if (masterFd >= 0) { close(masterFd); masterFd = -1; }
#endif
    }
};

} // namespace NeuroShell::PTY
