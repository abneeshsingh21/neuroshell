#pragma once
// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Proprietary and Confidential - see LICENSE.txt

#include <string>
#include <vector>
#include <mutex>
#include <chrono>
#include <sstream>
#include <iostream>
#include <cstdlib>

#if defined(_WIN32)
    #define WIN32_LEAN_AND_MEAN
    #include <windows.h>
#else
    #include <sys/socket.h>
    #include <sys/un.h>
    #include <unistd.h>
    #include <poll.h>
#endif

namespace NeuroShell::IPC {

struct TranslationResult {
    std::string command;
    std::string explanation;
    std::string risk_level = "SAFE";
    double confidence = 0.0;
    bool success = false;
};

struct DiagnosticResult {
    std::string category = "general_error";
    std::string root_cause;
    std::string auto_fix;
    double confidence = 0.0;
    bool success = false;
};

struct AgentPlanStep {
    int order = 1;
    std::string command;
    std::string description;
    std::string risk = "SAFE";
};

struct AgentPlanResult {
    std::string plan_id;
    std::string task;
    std::vector<AgentPlanStep> steps;
    bool success = false;
};

class NeuroIPCClient {
private:
#if defined(_WIN32)
    HANDLE hPipe = INVALID_HANDLE_VALUE;
    const std::wstring pipeName = L"\\\\.\\pipe\\neuroshell_ipc";
#else
    int sockFd = -1;
    std::string socketPath;
#endif
    std::mutex clientMutex;
    bool isConnected = false;

    // Fast lightweight JSON string extractor
    static std::string ExtractStringField(const std::string& json, const std::string& key) {
        std::string pattern = "\"" + key + "\"";
        size_t pos = json.find(pattern);
        if (pos == std::string::npos) return "";

        size_t colon = json.find(':', pos + pattern.length());
        if (colon == std::string::npos) return "";

        size_t startQuote = json.find('"', colon + 1);
        if (startQuote == std::string::npos) return "";

        std::string res;
        for (size_t i = startQuote + 1; i < json.length(); ++i) {
            if (json[i] == '\\' && i + 1 < json.length()) {
                res += json[i + 1];
                ++i;
            } else if (json[i] == '"') {
                break;
            } else {
                res += json[i];
            }
        }
        return res;
    }

    static double ExtractDoubleField(const std::string& json, const std::string& key, double defaultVal = 0.0) {
        std::string pattern = "\"" + key + "\"";
        size_t pos = json.find(pattern);
        if (pos == std::string::npos) return defaultVal;

        size_t colon = json.find(':', pos + pattern.length());
        if (colon == std::string::npos) return defaultVal;

        size_t valStart = json.find_first_not_of(" \t\r\n", colon + 1);
        if (valStart == std::string::npos) return defaultVal;

        try {
            return std::stod(json.substr(valStart));
        } catch (...) {
            return defaultVal;
        }
    }

    static std::string EscapeJSON(const std::string& s) {
        std::ostringstream o;
        for (char c : s) {
            switch (c) {
            case '"': o << "\\\""; break;
            case '\\': o << "\\\\"; break;
            case '\b': o << "\\b"; break;
            case '\f': o << "\\f"; break;
            case '\n': o << "\\n"; break;
            case '\r': o << "\\r"; break;
            case '\t': o << "\\t"; break;
            default:
                if ('\x00' <= c && c <= '\x1f') {
                    o << "\\u" << std::hex << (int)c;
                } else {
                    o << c;
                }
            }
        }
        return o.str();
    }

    bool ConnectInternal() {
#if defined(_WIN32)
        if (WaitNamedPipeW(pipeName.c_str(), 100)) {
            hPipe = CreateFileW(
                pipeName.c_str(),
                GENERIC_READ | GENERIC_WRITE,
                0, NULL, OPEN_EXISTING,
                0, NULL
            );
            if (hPipe != INVALID_HANDLE_VALUE) {
                isConnected = true;
                return true;
            }
        }
#else
        sockFd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (sockFd >= 0) {
            struct sockaddr_un addr{};
            addr.sun_family = AF_UNIX;
            strncpy(addr.sun_path, socketPath.c_str(), sizeof(addr.sun_path) - 1);
            if (connect(sockFd, (struct sockaddr*)&addr, sizeof(addr)) == 0) {
                isConnected = true;
                return true;
            }
            close(sockFd);
            sockFd = -1;
        }
#endif
        isConnected = false;
        return false;
    }

public:
    NeuroIPCClient() {
#if !defined(_WIN32)
        const char* home = getenv("HOME");
        socketPath = (home ? std::string(home) : "") + "/.neuroshell/ipc.sock";
#endif
    }

    ~NeuroIPCClient() { Disconnect(); }

    bool EnsureConnected() {
        std::lock_guard<std::mutex> lock(clientMutex);
        if (isConnected) return true;
        return ConnectInternal();
    }

    void Disconnect() {
#if defined(_WIN32)
        if (hPipe != INVALID_HANDLE_VALUE) {
            CloseHandle(hPipe);
            hPipe = INVALID_HANDLE_VALUE;
        }
#else
        if (sockFd >= 0) {
            close(sockFd);
            sockFd = -1;
        }
#endif
        isConnected = false;
    }

    std::string SendRawRPC(const std::string& payload, int timeoutMs = 5000) {
        if (!EnsureConnected()) return "";

        std::lock_guard<std::mutex> lock(clientMutex);
        std::string framed = payload + "\n";

#if defined(_WIN32)
        DWORD written = 0;
        if (!WriteFile(hPipe, framed.data(), (DWORD)framed.size(), &written, NULL)) {
            Disconnect();
            return "";
        }

        std::string response;
        char buffer[16384];
        DWORD bytesRead = 0;
        if (ReadFile(hPipe, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
            buffer[bytesRead] = '\0';
            response = buffer;
        }
        return response;
#else
        if (send(sockFd, framed.data(), framed.size(), 0) < 0) {
            Disconnect();
            return "";
        }

        struct pollfd pfd = { sockFd, POLLIN, 0 };
        if (poll(&pfd, 1, timeoutMs) > 0) {
            char buffer[16384];
            ssize_t n = recv(sockFd, buffer, sizeof(buffer) - 1, 0);
            if (n > 0) {
                buffer[n] = '\0';
                return std::string(buffer);
            }
        }
        return "";
#endif
    }

    bool Ping() {
        std::string req = "{\"jsonrpc\":\"2.0\",\"method\":\"ping\",\"params\":{},\"id\":1}";
        std::string resp = SendRawRPC(req, 400);
        return resp.find("\"result\": \"pong\"") != std::string::npos ||
               resp.find("\"result\":\"pong\"") != std::string::npos;
    }

    TranslationResult Translate(const std::string& query, const std::string& cwd) {
        TranslationResult res;
        std::string req = "{\"jsonrpc\":\"2.0\",\"method\":\"translate\",\"params\":{\"query\":\"" +
                          EscapeJSON(query) + "\",\"cwd\":\"" + EscapeJSON(cwd) + "\"},\"id\":2}";
        std::string resp = SendRawRPC(req, 8000);
        if (resp.empty() || resp.find("\"error\"") != std::string::npos) return res;

        res.command = ExtractStringField(resp, "command");
        res.explanation = ExtractStringField(resp, "explanation");
        res.risk_level = ExtractStringField(resp, "risk_level");
        if (res.risk_level.empty()) res.risk_level = "SAFE";
        res.confidence = ExtractDoubleField(resp, "confidence", 0.9);
        res.success = !res.command.empty();
        return res;
    }

    DiagnosticResult DiagnoseError(const std::string& command, const std::string& output, int exitCode, const std::string& cwd) {
        DiagnosticResult res;
        std::string req = "{\"jsonrpc\":\"2.0\",\"method\":\"diagnose_error\",\"params\":{\"command\":\"" +
                          EscapeJSON(command) + "\",\"output\":\"" + EscapeJSON(output) +
                          "\",\"exit_code\":" + std::to_string(exitCode) + ",\"cwd\":\"" + EscapeJSON(cwd) + "\"},\"id\":3}";
        std::string resp = SendRawRPC(req, 8000);
        if (resp.empty()) return res;

        res.category = ExtractStringField(resp, "category");
        res.root_cause = ExtractStringField(resp, "root_cause");
        res.auto_fix = ExtractStringField(resp, "auto_fix");
        res.confidence = ExtractDoubleField(resp, "confidence", 0.8);
        res.success = !res.root_cause.empty();
        return res;
    }

    AgentPlanResult CreateAgentPlan(const std::string& task, const std::string& cwd) {
        AgentPlanResult res;
        std::string req = "{\"jsonrpc\":\"2.0\",\"method\":\"agent_plan\",\"params\":{\"task\":\"" +
                          EscapeJSON(task) + "\",\"cwd\":\"" + EscapeJSON(cwd) + "\"},\"id\":4}";
        std::string resp = SendRawRPC(req, 12000);
        if (resp.empty()) return res;

        res.plan_id = ExtractStringField(resp, "plan_id");
        res.task = task;

        // Parse steps array
        size_t stepsPos = resp.find("\"steps\":");
        if (stepsPos != std::string::npos) {
            size_t arrStart = resp.find('[', stepsPos);
            size_t arrEnd = resp.find(']', arrStart);
            if (arrStart != std::string::npos && arrEnd != std::string::npos) {
                std::string stepsBlock = resp.substr(arrStart, arrEnd - arrStart + 1);
                size_t itemStart = 0;
                while ((itemStart = stepsBlock.find('{', itemStart)) != std::string::npos) {
                    size_t itemEnd = stepsBlock.find('}', itemStart);
                    if (itemEnd == std::string::npos) break;
                    std::string item = stepsBlock.substr(itemStart, itemEnd - itemStart + 1);

                    AgentPlanStep step;
                    step.command = ExtractStringField(item, "command");
                    step.description = ExtractStringField(item, "description");
                    step.risk = ExtractStringField(item, "risk");
                    if (step.risk.empty()) step.risk = "SAFE";
                    step.order = (int)ExtractDoubleField(item, "order", (double)(res.steps.size() + 1));

                    if (!step.command.empty()) {
                        res.steps.push_back(step);
                    }
                    itemStart = itemEnd + 1;
                }
            }
        }

        res.success = !res.steps.empty();
        return res;
    }

    std::string AIPipe(const std::string& directive, const std::string& prompt, const std::string& inputText, const std::string& cwd) {
        std::string req = "{\"jsonrpc\":\"2.0\",\"method\":\"ai_pipe\",\"params\":{\"directive\":\"" +
                          EscapeJSON(directive) + "\",\"prompt\":\"" + EscapeJSON(prompt) +
                          "\",\"input_text\":\"" + EscapeJSON(inputText) + "\",\"cwd\":\"" + EscapeJSON(cwd) + "\"},\"id\":5}";
        std::string resp = SendRawRPC(req, 15000);
        return ExtractStringField(resp, "response");
    }
};

} // namespace NeuroShell::IPC
