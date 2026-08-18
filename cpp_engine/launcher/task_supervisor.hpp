// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
#pragma once

#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <mutex>
#include <iostream>
#include <chrono>
#include <memory>
#include <sstream>
#include <algorithm>

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <signal.h>
#include <fcntl.h>
#endif

namespace neuroshell {

struct SupervisedTask {
    int id;
    std::string label;
    std::string command;
    std::string color_code;
    uint32_t pid{0};
    std::atomic<bool> is_running{false};
    int exit_code{0};

#if defined(_WIN32)
    HANDLE h_process{INVALID_HANDLE_VALUE};
    HANDLE h_job{INVALID_HANDLE_VALUE};
    HANDLE h_read_pipe{INVALID_HANDLE_VALUE};
#else
    pid_t pgid{0};
    int read_fd{-1};
#endif
};

class TaskSupervisor {
private:
    std::vector<std::shared_ptr<SupervisedTask>> tasks_;
    std::mutex tasks_lock_;
    std::atomic<bool> stop_requested_{false};
    std::vector<std::thread> reader_threads_;

    const std::vector<std::string> color_palette_ = {
        "\033[38;2;56;189;248m",  // Cyan
        "\033[38;2;74;222;128m",  // Green
        "\033[38;2;192;132;252m", // Magenta
        "\033[38;2;251;191;36m",  // Yellow
        "\033[38;2;248;113;113m", // Red
        "\033[38;2;94;234;212m",  // Teal
        "\033[38;2;244;114;182m", // Pink
        "\033[38;2;167;139;250m"  // Indigo
    };

public:
    TaskSupervisor() = default;

    ~TaskSupervisor() {
        StopAll();
    }

    void RunParallel(const std::vector<std::string>& commands, const std::vector<std::string>& labels = {}) {
        if (commands.empty()) return;

        StopAll();
        stop_requested_.store(false);

        std::cout << "\n\033[38;2;56;189;248m╭── ⌬ NeuroShell Multi-Process Supervisor ──────────────────────────────╮\033[0m\n";
        std::cout << "\033[38;2;56;189;248m│\033[0m  Spawning \033[1m" << commands.size() << "\033[0m parallel services. Press \033[1;33m[Ctrl+C]\033[0m to terminate all workers.\033[38;2;56;189;248m\033[0m\n";
        std::cout << "\033[38;2;56;189;248m╰───────────────────────────────────────────────────────────────────────╯\033[0m\n\n";

        for (size_t i = 0; i < commands.size(); ++i) {
            auto task = std::make_shared<SupervisedTask>();
            task->id = static_cast<int>(i + 1);
            task->command = commands[i];
            
            if (i < labels.size() && !labels[i].empty()) {
                task->label = labels[i];
            } else {
                // Auto generate label from command binary
                std::string firstWord = commands[i];
                size_t sp = firstWord.find(' ');
                if (sp != std::string::npos) firstWord = firstWord.substr(0, sp);
                task->label = firstWord + ":" + std::to_string(task->id);
            }

            task->color_code = color_palette_[i % color_palette_.size()];
            task->is_running.store(true);

            if (SpawnTask(task)) {
                tasks_.push_back(task);
            }
        }

        // Multiplexing thread to wait until all exit or stop is requested
        for (auto& task : tasks_) {
            reader_threads_.emplace_back([this, task]() {
                ReadTaskOutput(task);
            });
        }

        // Wait for all reader threads
        for (auto& th : reader_threads_) {
            if (th.joinable()) th.join();
        }
        reader_threads_.clear();

        std::cout << "\n\033[38;2;100;116;139m[NeuroShell] All parallel workers have stopped.\033[0m\n\n";
    }

    bool SpawnTask(std::shared_ptr<SupervisedTask> task) {
#if defined(_WIN32)
        // 1. Create Pipes for Output Multiplexing
        SECURITY_ATTRIBUTES saAttr;
        saAttr.nLength = sizeof(SECURITY_ATTRIBUTES);
        saAttr.bInheritHandle = TRUE;
        saAttr.lpSecurityDescriptor = NULL;

        HANDLE hChildStdOutRead = INVALID_HANDLE_VALUE;
        HANDLE hChildStdOutWrite = INVALID_HANDLE_VALUE;

        if (!CreatePipe(&hChildStdOutRead, &hChildStdOutWrite, &saAttr, 0)) {
            return false;
        }
        SetHandleInformation(hChildStdOutRead, HANDLE_FLAG_INHERIT, 0);

        // 2. Win32 Job Object for Zero-Zombie Process Tree Teardown
        HANDLE hJob = CreateJobObjectW(NULL, NULL);
        if (hJob != NULL) {
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli = { 0 };
            jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK;
            SetInformationJobObject(hJob, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));
            task->h_job = hJob;
        }

        // 3. Spawn Process
        STARTUPINFOA si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        si.cb = sizeof(si);
        si.hStdError = hChildStdOutWrite;
        si.hStdOutput = hChildStdOutWrite;
        si.dwFlags |= STARTF_USESTDHANDLES;
        ZeroMemory(&pi, sizeof(pi));

        std::string cmd = "cmd.exe /c \"" + task->command + "\"";
        std::vector<char> cmdBuf(cmd.begin(), cmd.end());
        cmdBuf.push_back(0);

        BOOL success = CreateProcessA(
            NULL, cmdBuf.data(), NULL, NULL, TRUE,
            CREATE_NO_WINDOW | CREATE_SUSPENDED | CREATE_BREAKAWAY_FROM_JOB,
            NULL, NULL, &si, &pi
        );

        CloseHandle(hChildStdOutWrite);

        if (!success) {
            CloseHandle(hChildStdOutRead);
            if (task->h_job != INVALID_HANDLE_VALUE) CloseHandle(task->h_job);
            return false;
        }

        if (task->h_job != INVALID_HANDLE_VALUE) {
            AssignProcessToJobObject(task->h_job, pi.hProcess);
        }

        ResumeThread(pi.hThread);
        CloseHandle(pi.hThread);

        task->pid = static_cast<uint32_t>(pi.dwProcessId);
        task->h_process = pi.hProcess;
        task->h_read_pipe = hChildStdOutRead;
        return true;

#else
        int pipefds[2];
        if (pipe(pipefds) != 0) return false;

        pid_t pid = fork();
        if (pid < 0) {
            close(pipefds[0]);
            close(pipefds[1]);
            return false;
        }

        if (pid == 0) {
            // Child process: establish own process group
            setpgid(0, 0);
            close(pipefds[0]);
            dup2(pipefds[1], STDOUT_FILENO);
            dup2(pipefds[1], STDERR_FILENO);
            close(pipefds[1]);

            const char* shell = getenv("SHELL");
            if (!shell) shell = "/bin/sh";
            execlp(shell, shell, "-c", task->command.c_str(), (char*)NULL);
            _exit(127);
        }

        close(pipefds[1]);
        task->pid = static_cast<uint32_t>(pid);
        task->pgid = pid;
        task->read_fd = pipefds[0];
        return true;
#endif
    }

    void ReadTaskOutput(std::shared_ptr<SupervisedTask> task) {
        char buffer[2048];
        std::string lineAccumulator = "";

#if defined(_WIN32)
        DWORD bytesRead = 0;
        while (!stop_requested_.load() && ReadFile(task->h_read_pipe, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
            buffer[bytesRead] = 0;
            lineAccumulator += buffer;

            size_t pos = 0;
            while ((pos = lineAccumulator.find('\n')) != std::string::npos) {
                std::string line = lineAccumulator.substr(0, pos);
                if (!line.empty() && line.back() == '\r') line.pop_back();
                lineAccumulator.erase(0, pos + 1);

                std::lock_guard<std::mutex> lock(tasks_lock_);
                std::cout << task->color_code << "[" << task->label << "]\033[0m " << line << "\n";
                std::cout.flush();
            }
        }

        if (task->h_process != INVALID_HANDLE_VALUE) {
            WaitForSingleObject(task->h_process, INFINITE);
            DWORD exitCode = 0;
            GetExitCodeProcess(task->h_process, &exitCode);
            task->exit_code = static_cast<int>(exitCode);
            CloseHandle(task->h_process);
            task->h_process = INVALID_HANDLE_VALUE;
        }
        if (task->h_read_pipe != INVALID_HANDLE_VALUE) {
            CloseHandle(task->h_read_pipe);
            task->h_read_pipe = INVALID_HANDLE_VALUE;
        }
        if (task->h_job != INVALID_HANDLE_VALUE) {
            CloseHandle(task->h_job);
            task->h_job = INVALID_HANDLE_VALUE;
        }
#else
        ssize_t bytesRead = 0;
        while (!stop_requested_.load() && (bytesRead = read(task->read_fd, buffer, sizeof(buffer) - 1)) > 0) {
            buffer[bytesRead] = 0;
            lineAccumulator += buffer;

            size_t pos = 0;
            while ((pos = lineAccumulator.find('\n')) != std::string::npos) {
                std::string line = lineAccumulator.substr(0, pos);
                if (!line.empty() && line.back() == '\r') line.pop_back();
                lineAccumulator.erase(0, pos + 1);

                std::lock_guard<std::mutex> lock(tasks_lock_);
                std::cout << task->color_code << "[" << task->label << "]\033[0m " << line << "\n";
                std::cout.flush();
            }
        }

        if (task->read_fd >= 0) {
            close(task->read_fd);
            task->read_fd = -1;
        }
        if (task->pid > 0) {
            int status = 0;
            waitpid(static_cast<pid_t>(task->pid), &status, 0);
            if (WIFEXITED(status)) task->exit_code = WEXITSTATUS(status);
        }
#endif
        task->is_running.store(false);
    }

    void StopAll() {
        stop_requested_.store(true);
        std::lock_guard<std::mutex> lock(tasks_lock_);

        for (auto& task : tasks_) {
            if (task->is_running.load()) {
#if defined(_WIN32)
                if (task->h_job != INVALID_HANDLE_VALUE) {
                    TerminateJobObject(task->h_job, 1);
                    CloseHandle(task->h_job);
                    task->h_job = INVALID_HANDLE_VALUE;
                }
                if (task->h_process != INVALID_HANDLE_VALUE) {
                    TerminateProcess(task->h_process, 1);
                }
#else
                if (task->pgid > 0) {
                    kill(-task->pgid, SIGTERM);
                }
#endif
                task->is_running.store(false);
            }
        }
    }

    void PrintDashboard() {
        std::lock_guard<std::mutex> lock(tasks_lock_);
        std::cout << "\n\033[38;2;56;189;248m╭── ⌬ NeuroShell Task Supervisor ──────────────────────────────────╮\033[0m\n";
        std::cout << "\033[38;2;56;189;248m│\033[0m ID  Label          PID      Status    Command\033[38;2;56;189;248m\033[0m\n";
        std::cout << "\033[38;2;56;189;248m├──────────────────────────────────────────────────────────────────┤\033[0m\n";

        if (tasks_.empty()) {
            std::cout << "\033[38;2;56;189;248m│\033[0m  \033[38;2;100;116;139mNo active background services running.\033[0m\n";
        } else {
            for (const auto& t : tasks_) {
                std::string statusStr = t->is_running.load() ? "\033[38;2;74;222;128mRUNNING\033[0m" : "\033[38;2;100;116;139mSTOPPED\033[0m";
                std::cout << "\033[38;2;56;189;248m│\033[0m  " << t->id << "  " << t->label << "  " << t->pid << "  " << statusStr << "  " << t->command << "\n";
            }
        }
        std::cout << "\033[38;2;56;189;248m╰──────────────────────────────────────────────────────────────────╯\033[0m\n\n";
    }
};

} // namespace neuroshell
