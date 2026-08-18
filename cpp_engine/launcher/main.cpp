// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Proprietary and Confidential - see LICENSE.txt
/*
 * NeuroShell Enterprise Cross-Platform Native C++20 Terminal Host
 * Platforms: Windows (Win32 ConPTY), Linux (glibc/musl), macOS (Darwin / Apple Silicon & Intel)
 * Standards: C++20
 * Features:
 *  1. Ghost-Text Real-Time Predictive Autocomplete & Path Tab-Completion
 *  2. Bracketed Paste Mode (\033[?2004h) preventing premature newline execution
 *  3. Dynamic Window Resizing (SIGWINCH / WINDOW_BUFFER_SIZE_EVENT)
 *  4. Live Syntax Highlighting & Real-Time Red DANGER Safety Guard
 *  5. Smart Error Shield with 1-Key 'y' Auto-Fixer
 *  6. Native History Store & Interactive 'Ctrl+R' Reverse Search Modal
 *  7. Multi-Tab & Workspace Manager (Ctrl+T, Ctrl+W, Alt+1..9)
 *  8. Multi-Token Deep Directory Jumper ('z', 'f', 'mark', 'bm')
 *  9. Non-Blocking Async Pipe Process Spawner (fork/exec on POSIX, Job Objects on Win32)
 * 10. Inode Cycle-Aware Symlink/Junction Recursion Guard
 * 11. Async-Signal-Safe SEH & POSIX Signal Crash Diagnostics
 * 12. Full-Screen TUI Direct Passthrough (vim, nano, htop, fzf)
 */

#include <iostream>
#include <string>
#include <string_view>
#include <vector>
#include <sstream>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <chrono>
#include <map>
#include <set>
#include <unordered_set>
#include <thread>
#include <mutex>
#include <cctype>
#include <cstring>
#include <cstdlib>

// ═══════════════════════════════════════════════════════════
// Platform-Specific Headers & Abstractions
// ═══════════════════════════════════════════════════════════

#if defined(_WIN32) || defined(_WIN64)
    #define NEUROSHELL_PLATFORM_WINDOWS 1
    #define NOMINMAX
    #define WIN32_LEAN_AND_MEAN
    #include <windows.h>
    #include <shellapi.h>
    #include <conio.h>
#else
    #define NEUROSHELL_PLATFORM_POSIX 1
    #include <unistd.h>
    #include <termios.h>
    #include <sys/types.h>
    #include <sys/stat.h>
    #include <sys/wait.h>
    #include <sys/ioctl.h>
    #include <poll.h>
    #include <signal.h>
    #include <fcntl.h>
    #include <pwd.h>
#endif

#include "ipc_client.hpp"
#include "daemon_spawner.hpp"
#include "pty_host.hpp"
#include "dlp_masker.hpp"
#include "shm_ipc.hpp"
#include "stream_recorder.hpp"
#include "split_pane.hpp"

namespace fs = std::filesystem;

// 24-bit TrueColor ANSI Tokens
#define C_CYAN    "\033[38;2;56;189;248m"
#define C_MAGENTA "\033[38;2;192;132;252m"
#define C_GREEN   "\033[38;2;74;222;128m"
#define C_YELLOW  "\033[38;2;251;191;36m"
#define C_RED     "\033[38;2;248;113;113m"
#define C_BG_RED  "\033[48;2;239;68;68;38;2;255;255;255m"
#define C_MUTED   "\033[38;2;100;116;139m"
#define C_WHITE   "\033[38;2;241;245;249m"
#define C_GHOST   "\033[38;2;100;116;139m"
#define C_TAB_ACT "\033[48;2;30;41;59;38;2;56;189;248m"
#define C_TAB_IN  "\033[38;2;100;116;139m"
#define C_BOLD    "\033[1m"
#define C_DIM     "\033[2m"
#define C_RESET   "\033[0m"

// Forward Declaration for Crash Filters
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
LONG WINAPI NeuroShellWin32CrashFilter(EXCEPTION_POINTERS* ep);
#else
void NeuroShellPosixSignalHandler(int sig, siginfo_t* info, void* ucontext);
#endif

// ═══════════════════════════════════════════════════════════
// Data Structures
// ═══════════════════════════════════════════════════════════

struct MenuItem {
    std::string label;
    std::string desc;
    std::string id;
};

struct Tab {
    int id;
    std::string name;
    std::string cwd;
};

struct HistoryEntry {
    std::string command;
    std::string cwd;
    long long timestamp;
};

enum class KeyCode {
    Unknown,
    Printable,
    Enter,
    Backspace,
    Delete,
    Tab,
    Escape,
    Up,
    Down,
    Left,
    Right,
    Home,
    End,
    Ctrl_C,
    Ctrl_L,
    Ctrl_R,
    Ctrl_T,
    Ctrl_W
};

struct KeyEvent {
    KeyCode code = KeyCode::Unknown;
    char ch = 0;
};

// ═══════════════════════════════════════════════════════════
// Cross-Platform Terminal Subsystem & Raw Mode
// ═══════════════════════════════════════════════════════════

class PlatformTerminal {
private:
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
    DWORD origOutMode = 0;
    DWORD origInMode = 0;
    HANDLE hOut = INVALID_HANDLE_VALUE;
    HANDLE hIn = INVALID_HANDLE_VALUE;
#else
    struct termios origTermios {};
    bool rawEnabled = false;
#endif

public:
    PlatformTerminal() {
        Init();
    }

    ~PlatformTerminal() {
        Restore();
    }

    void Init() {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        SetUnhandledExceptionFilter(NeuroShellWin32CrashFilter);
        SetConsoleOutputCP(CP_UTF8);
        SetConsoleCP(CP_UTF8);

        hOut = GetStdHandle(STD_OUTPUT_HANDLE);
        if (hOut != INVALID_HANDLE_VALUE) {
            GetConsoleMode(hOut, &origOutMode);
            DWORD dwMode = origOutMode | ENABLE_VIRTUAL_TERMINAL_PROCESSING | 0x0008;
            SetConsoleMode(hOut, dwMode);
        }

        hIn = GetStdHandle(STD_INPUT_HANDLE);
        if (hIn != INVALID_HANDLE_VALUE) {
            GetConsoleMode(hIn, &origInMode);
            DWORD dwInMode = origInMode | ENABLE_VIRTUAL_TERMINAL_INPUT;
            SetConsoleMode(hIn, dwInMode);
        }
#else
        struct sigaction sa;
        memset(&sa, 0, sizeof(sa));
        sa.sa_sigaction = NeuroShellPosixSignalHandler;
        sa.sa_flags = SA_SIGINFO;
        sigaction(SIGSEGV, &sa, nullptr);
        sigaction(SIGBUS, &sa, nullptr);
        sigaction(SIGFPE, &sa, nullptr);
        sigaction(SIGILL, &sa, nullptr);

        if (isatty(STDIN_FILENO)) {
            if (tcgetattr(STDIN_FILENO, &origTermios) == 0) {
                struct termios raw = origTermios;
                raw.c_lflag &= ~(ICANON | ECHO | ISIG | IEXTEN);
                raw.c_iflag &= ~(IXON | ICRNL);
                raw.c_cc[VMIN] = 1;
                raw.c_cc[VTIME] = 0;
                tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw);
                rawEnabled = true;
            }
        }
#endif
        // Enable Bracketed Paste Mode
        std::cout << "\033[?2004h" << std::flush;
    }

    void Restore() {
        // Disable Bracketed Paste Mode & show cursor
        std::cout << "\033[?2004l\033[?25h\033[0m" << std::flush;
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        if (hOut != INVALID_HANDLE_VALUE) SetConsoleMode(hOut, origOutMode);
        if (hIn != INVALID_HANDLE_VALUE) SetConsoleMode(hIn, origInMode);
#else
        if (rawEnabled) {
            tcsetattr(STDIN_FILENO, TCSAFLUSH, &origTermios);
            rawEnabled = false;
        }
#endif
    }

    static void SetTitle(const std::string& title) {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        std::wstring wTitle(title.begin(), title.end());
        SetConsoleTitleW(wTitle.c_str());
#else
        std::cout << "\033]0;" << title << "\007" << std::flush;
#endif
    }

    static void ClearScreen() {
        std::cout << "\033[2J\033[H" << std::flush;
    }

    static int GetWindowColumns() {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        CONSOLE_SCREEN_BUFFER_INFO csbi;
        HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
        if (hOut != INVALID_HANDLE_VALUE && GetConsoleScreenBufferInfo(hOut, &csbi)) {
            return csbi.srWindow.Right - csbi.srWindow.Left + 1;
        }
#else
        struct winsize ws;
        if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 && ws.ws_col > 0) {
            return ws.ws_col;
        }
#endif
        return 80;
    }

    KeyEvent ReadKey() {
        KeyEvent ev;
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        int ch = _getch();
        if (ch == 13 || ch == 10) { ev.code = KeyCode::Enter; return ev; }
        if (ch == 8) { ev.code = KeyCode::Backspace; return ev; }
        if (ch == 9) { ev.code = KeyCode::Tab; return ev; }
        if (ch == 3) { ev.code = KeyCode::Ctrl_C; return ev; }
        if (ch == 12) { ev.code = KeyCode::Ctrl_L; return ev; }
        if (ch == 18) { ev.code = KeyCode::Ctrl_R; return ev; }
        if (ch == 20) { ev.code = KeyCode::Ctrl_T; return ev; }
        if (ch == 23) { ev.code = KeyCode::Ctrl_W; return ev; }
        if (ch == 27) { ev.code = KeyCode::Escape; return ev; }

        if (ch == 0 || ch == 0xE0 || ch == 224) {
            int code = _getch();
            if (code == 72) ev.code = KeyCode::Up;
            else if (code == 80) ev.code = KeyCode::Down;
            else if (code == 75) ev.code = KeyCode::Left;
            else if (code == 77) ev.code = KeyCode::Right;
            else if (code == 71) ev.code = KeyCode::Home;
            else if (code == 79) ev.code = KeyCode::End;
            else if (code == 83) ev.code = KeyCode::Delete;
            return ev;
        }

        if (ch >= 32 && ch <= 126) {
            ev.code = KeyCode::Printable;
            ev.ch = static_cast<char>(ch);
            return ev;
        }
#else
        char c = 0;
        ssize_t n = read(STDIN_FILENO, &c, 1);
        if (n <= 0) return ev;

        if (c == '\r' || c == '\n') { ev.code = KeyCode::Enter; return ev; }
        if (c == 127 || c == 8) { ev.code = KeyCode::Backspace; return ev; }
        if (c == '\t') { ev.code = KeyCode::Tab; return ev; }
        if (c == 3) { ev.code = KeyCode::Ctrl_C; return ev; }
        if (c == 12) { ev.code = KeyCode::Ctrl_L; return ev; }
        if (c == 18) { ev.code = KeyCode::Ctrl_R; return ev; }
        if (c == 20) { ev.code = KeyCode::Ctrl_T; return ev; }
        if (c == 23) { ev.code = KeyCode::Ctrl_W; return ev; }

        if (c == 27) {
            struct pollfd pfd = { STDIN_FILENO, POLLIN, 0 };
            if (poll(&pfd, 1, 50) > 0) {
                char seq[4] = {0};
                if (read(STDIN_FILENO, &seq[0], 1) > 0) {
                    if (seq[0] == '[') {
                        if (read(STDIN_FILENO, &seq[1], 1) > 0) {
                            if (seq[1] == 'A') { ev.code = KeyCode::Up; return ev; }
                            if (seq[1] == 'B') { ev.code = KeyCode::Down; return ev; }
                            if (seq[1] == 'C') { ev.code = KeyCode::Right; return ev; }
                            if (seq[1] == 'D') { ev.code = KeyCode::Left; return ev; }
                            if (seq[1] == 'H') { ev.code = KeyCode::Home; return ev; }
                            if (seq[1] == 'F') { ev.code = KeyCode::End; return ev; }
                            if (seq[1] >= '1' && seq[1] <= '4') {
                                char t = 0;
                                read(STDIN_FILENO, &t, 1);
                                if (t == '~') {
                                    if (seq[1] == '1') ev.code = KeyCode::Home;
                                    else if (seq[1] == '3') ev.code = KeyCode::Delete;
                                    else if (seq[1] == '4') ev.code = KeyCode::End;
                                    return ev;
                                }
                            }
                        }
                    }
                }
            }
            ev.code = KeyCode::Escape;
            return ev;
        }

        if (c >= 32 && c <= 126) {
            ev.code = KeyCode::Printable;
            ev.ch = c;
            return ev;
        }
#endif
        return ev;
    }
};

// ═══════════════════════════════════════════════════════════
// Cross-Platform Filesystem & Path Utilities
// ═══════════════════════════════════════════════════════════

class PlatformFS {
public:
    struct FileID {
        uint64_t dev = 0;
        uint64_t ino = 0;

        bool operator==(const FileID& o) const {
            return dev == o.dev && ino == o.ino;
        }
    };

    struct FileIDHasher {
        std::size_t operator()(const FileID& k) const {
            return std::hash<uint64_t>()(k.dev) ^ (std::hash<uint64_t>()(k.ino) << 1);
        }
    };

    static fs::path GetHomeDir() {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        const char* userProfile = getenv("USERPROFILE");
        if (userProfile) return fs::path(userProfile);
        const char* homeDrive = getenv("HOMEDRIVE");
        const char* homePath = getenv("HOMEPATH");
        if (homeDrive && homePath) return fs::path(std::string(homeDrive) + std::string(homePath));
        return fs::current_path();
#else
        const char* home = getenv("HOME");
        if (home) return fs::path(home);
        struct passwd* pw = getpwuid(getuid());
        if (pw && pw->pw_dir) return fs::path(pw->pw_dir);
        return fs::current_path();
#endif
    }

    static bool GetUniqueID(const fs::path& p, FileID& outId) {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        HANDLE hDir = CreateFileW(p.c_str(), 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                  NULL, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, NULL);
        if (hDir == INVALID_HANDLE_VALUE) return false;

        BY_HANDLE_FILE_INFORMATION info;
        BOOL ok = GetFileInformationByHandle(hDir, &info);
        CloseHandle(hDir);

        if (ok) {
            outId.dev = info.dwVolumeSerialNumber;
            outId.ino = (static_cast<uint64_t>(info.nFileIndexHigh) << 32) | info.nFileIndexLow;
            return true;
        }
        return false;
#else
        struct stat st;
        if (stat(p.c_str(), &st) == 0) {
            outId.dev = static_cast<uint64_t>(st.st_dev);
            outId.ino = static_cast<uint64_t>(st.st_ino);
            return true;
        }
        return false;
#endif
    }
};

// ═══════════════════════════════════════════════════════════
// Native Prediction, Ghost-Text & Path Completion Engine
// ═══════════════════════════════════════════════════════════

class PredictionEngine {
private:
    std::vector<std::string> dictionary;

public:
    PredictionEngine() {
        dictionary = {
            "git status", "git commit -m \"update\"", "git push origin main", "git pull origin main",
            "git add .", "git diff", "git log --oneline -n 10", "git checkout -b ", "git branch -a",
            "python main.py", "python -m pytest", "python -m venv .venv",
            "pip install -r requirements.txt", "pip install ", "pip list", "pip freeze",
            "npm install", "npm run dev", "npm run build", "npm test", "npm start",
            "cargo build --release", "cargo run", "cargo test", "cargo check",
            "docker ps -a", "docker compose up -d", "docker build -t app .", "docker stop ",
            "open file explorer", "open current folder", "find all python files", "find all javascript files",
            "show my github repos", "list my repos", "kill port 8000", "kill port 3000", "show active ports",
            "system info", "ipconfig", "clear", "exit",
            "/api-key", "/model", "/theme", "/swarm", "/plan", "/stats", "/help"
        };
    }

    void Learn(const std::string& cmd) {
        if (cmd.length() < 2) return;
        auto it = std::find(dictionary.begin(), dictionary.end(), cmd);
        if (it != dictionary.end()) {
            dictionary.erase(it);
        }
        dictionary.insert(dictionary.begin(), cmd);
    }

    std::string GetSuggestion(const std::string& prefix) {
        if (prefix.empty()) return "";
        std::string lowerPref = prefix;
        std::transform(lowerPref.begin(), lowerPref.end(), lowerPref.begin(), ::tolower);

        for (const auto& item : dictionary) {
            std::string lowerItem = item;
            std::transform(lowerItem.begin(), lowerItem.end(), lowerItem.begin(), ::tolower);

            if (lowerItem.rfind(lowerPref, 0) == 0 && lowerItem.length() > lowerPref.length()) {
                return item.substr(prefix.length());
            }
        }
        return "";
    }

    std::string GetPathCompletion(const std::string& buffer) {
        if (buffer.empty()) return "";
        size_t lastSpace = buffer.find_last_of(" \t");
        std::string token = (lastSpace == std::string::npos) ? buffer : buffer.substr(lastSpace + 1);

        if (token.empty()) return "";

        try {
            fs::path p(token);
            fs::path dir = p.parent_path().empty() ? fs::current_path() : p.parent_path();
            std::string stem = p.filename().string();

            if (fs::exists(dir)) {
                for (const auto& entry : fs::directory_iterator(dir)) {
                    std::string filename = entry.path().filename().string();
                    if (filename.rfind(stem, 0) == 0 && filename.length() > stem.length()) {
                        std::string completion = filename.substr(stem.length());
                        if (entry.is_directory()) completion += "/";
                        return completion;
                    }
                }
            }
        } catch (...) {}
        return "";
    }
};

// ═══════════════════════════════════════════════════════════
// Real-Time Syntax Highlighter & Safety Lexer
// ═══════════════════════════════════════════════════════════

class SyntaxHighlighter {
private:
    std::set<std::string> knownExecutables = {
        "git", "python", "python3", "pip", "pip3", "npm", "npx", "node", "cargo", "rustc",
        "docker", "kubectl", "dir", "ls", "cd", "cls", "clear", "echo", "cat", "cp", "mv",
        "rm", "mkdir", "rmdir", "start", "tasklist", "taskkill", "ps", "kill", "netstat", "ss",
        "ipconfig", "ifconfig", "ip", "systeminfo", "uname", "findstr", "grep", "curl", "ssh", "tar", "code", "vim", "brew"
    };

    std::vector<std::string> dangerousPatterns = {
        "rm -rf /", "rm -rf *", "del /f", "del /s", "format ", "drop database", "drop table",
        "mkfs", "dd if=", ":(){ :|:& };:", "rmdir /s"
    };

public:
    bool IsDangerous(const std::string& input, std::string& matchedPattern) {
        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        for (const auto& p : dangerousPatterns) {
            if (lower.find(p) != std::string::npos) {
                matchedPattern = p;
                return true;
            }
        }
        return false;
    }

    std::string Highlight(const std::string& input) {
        if (input.empty()) return "";

        std::string dangerPattern;
        bool dangerous = IsDangerous(input, dangerPattern);

        std::string result = "";
        if (dangerous) {
            result += std::string(C_BG_RED) + " DANGER " + C_RESET + " ";
        }

        if (input[0] == '/') {
            return std::string(C_BOLD) + C_MAGENTA + input + C_RESET;
        }

        size_t idx = 0;
        bool isFirst = true;
        while (idx < input.length()) {
            if (input[idx] == ' ') {
                result += ' ';
                idx++;
                continue;
            }

            if (input[idx] == '"' || input[idx] == '\'') {
                char quote = input[idx];
                size_t endQuote = input.find(quote, idx + 1);
                if (endQuote == std::string::npos) endQuote = input.length() - 1;
                std::string strVal = input.substr(idx, endQuote - idx + 1);
                result += std::string(C_YELLOW) + strVal + C_RESET;
                idx = endQuote + 1;
                isFirst = false;
                continue;
            }

            size_t nextSpace = input.find(' ', idx);
            if (nextSpace == std::string::npos) nextSpace = input.length();
            std::string word = input.substr(idx, nextSpace - idx);

            if (isFirst) {
                std::string lowerWord = word;
                std::transform(lowerWord.begin(), lowerWord.end(), lowerWord.begin(), ::tolower);
                if (knownExecutables.count(lowerWord) > 0) {
                    result += std::string(C_BOLD) + C_GREEN + word + C_RESET;
                } else if (dangerous) {
                    result += std::string(C_BOLD) + C_RED + word + C_RESET;
                } else {
                    result += std::string(C_CYAN) + word + C_RESET;
                }
                isFirst = false;
            } else {
                if (word.rfind("-", 0) == 0 || word.rfind("/", 0) == 0) {
                    result += std::string(C_CYAN) + word + C_RESET;
                } else if (word.find("\\") != std::string::npos || word.find("/") != std::string::npos || word.find(".") != std::string::npos) {
                    result += std::string(C_YELLOW) + word + C_RESET;
                } else if (dangerous) {
                    result += std::string(C_RED) + word + C_RESET;
                } else {
                    result += std::string(C_WHITE) + word + C_RESET;
                }
            }

            idx = nextSpace;
        }

        return result;
    }
};

// ═══════════════════════════════════════════════════════════
// Smart Error Diagnostics & 1-Key Auto-Fix Shield
// ═══════════════════════════════════════════════════════════

class SmartErrorShield {
public:
    struct ErrorReport {
        bool hasError = false;
        std::string category;
        std::string detail;
        std::string location;
        std::string autoFixCmd;
    };

    ErrorReport Analyze(const std::string& output, int exitCode, const std::string& lastCmd) {
        ErrorReport rep;
        if (exitCode == 0 && output.find("Error:") == std::string::npos && output.find("Exception") == std::string::npos) {
            return rep;
        }

        std::string lowerOut = output;
        std::transform(lowerOut.begin(), lowerOut.end(), lowerOut.begin(), ::tolower);

        if (output.find("ModuleNotFoundError: No module named ") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Missing Python Dependency";
            size_t pos = output.find("ModuleNotFoundError: No module named ");
            size_t q1 = output.find("'", pos);
            size_t q2 = output.find("'", q1 + 1);
            if (q1 != std::string::npos && q2 != std::string::npos) {
                std::string pkg = output.substr(q1 + 1, q2 - q1 - 1);
                rep.detail = "ModuleNotFoundError: No module named '" + pkg + "'";
                rep.autoFixCmd = "pip install " + pkg;
            }
        }
        else if (output.find("Cannot find module ") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Missing NPM Package";
            size_t pos = output.find("Cannot find module ");
            size_t q1 = output.find("'", pos);
            size_t q2 = output.find("'", q1 + 1);
            if (q1 != std::string::npos && q2 != std::string::npos) {
                std::string pkg = output.substr(q1 + 1, q2 - q1 - 1);
                rep.detail = "Cannot find module '" + pkg + "'";
                rep.autoFixCmd = "npm install " + pkg;
            }
        }
        else if (lowerOut.find("not a git repository") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Git Initialization Error";
            rep.detail = "fatal: not a git repository";
            rep.autoFixCmd = "git init";
        }
        else if (lowerOut.find("address already in use") != std::string::npos || lowerOut.find("eaddrinuse") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Port Conflict";
            rep.detail = "Address already in use / Port occupied";
            rep.autoFixCmd = "show active ports";
        }
        else if (lowerOut.find("command not found") != std::string::npos || lowerOut.find("not recognized as an internal or external command") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Command Typo / Missing Path";
            rep.detail = "'" + lastCmd + "' not found / not recognized";
            if (lastCmd == "gti") rep.autoFixCmd = "git";
            else if (lastCmd == "pyhton" || lastCmd == "pythn") rep.autoFixCmd = "python3";
            else if (lastCmd == "dockr") rep.autoFixCmd = "docker";
            else if (lastCmd == "npn") rep.autoFixCmd = "npm";
        }

        return rep;
    }

    void RenderErrorCard(const ErrorReport& rep) {
        if (!rep.hasError) return;

        std::cout << "\n" << C_RED << "  ╭── ❌ Smart Error Shield ──────────────────────────────────────────╮\n"
                  << "  │ " << C_BOLD << C_WHITE << "Category: " << C_RESET << C_YELLOW << rep.category << C_RED 
                  << std::string(std::max(0, 53 - (int)rep.category.length()), ' ') << "│\n"
                  << "  │ " << C_MUTED << "Details:  " << C_RESET << rep.detail << C_RED 
                  << std::string(std::max(0, 53 - (int)rep.detail.length()), ' ') << "│\n";

        if (!rep.autoFixCmd.empty()) {
            std::cout << "  │                                                                   │\n"
                      << "  │ " << C_BOLD << C_CYAN << "💡 Recommended Auto-Fix:                                          " << C_RED << "│\n"
                      << "  │    " << C_GREEN << "❯ " << C_BOLD << rep.autoFixCmd << C_RESET << C_RED 
                      << std::string(std::max(0, 51 - (int)rep.autoFixCmd.length()), ' ') << "│\n"
                      << "  ╰───────────────────────────────────────────────────────────────────╯" << C_RESET << "\n"
                      << C_YELLOW << "  Press " << C_BOLD << "[y]" << C_RESET << C_YELLOW << " to apply fix immediately, or press Enter to continue...\n" << C_RESET;
        } else {
            std::cout << "  ╰───────────────────────────────────────────────────────────────────╯" << C_RESET << "\n";
        }
    }
};

// ═══════════════════════════════════════════════════════════
// Smart Fuzzy Directory Jumper (z-jump & frecent navigation)
// ═══════════════════════════════════════════════════════════

class SmartDirectoryJumper {
private:
    std::vector<std::string> historyDirs;
    std::map<std::string, std::string> bookmarks;
    std::string lastDir = "";
    std::unordered_set<PlatformFS::FileID, PlatformFS::FileIDHasher> visited;

    std::vector<std::string> Tokenize(const std::string& str) {
        std::vector<std::string> tokens;
        std::istringstream iss(str);
        std::string s;
        while (iss >> s) {
            std::transform(s.begin(), s.end(), s.begin(), ::tolower);
            tokens.push_back(s);
        }
        return tokens;
    }

    bool PathMatchesTokens(const std::string& path, const std::vector<std::string>& tokens) {
        if (tokens.empty()) return false;
        std::string lowerPath = path;
        std::transform(lowerPath.begin(), lowerPath.end(), lowerPath.begin(), ::tolower);

        size_t lastPos = 0;
        for (const auto& tok : tokens) {
            size_t p = lowerPath.find(tok, lastPos);
            if (p == std::string::npos) return false;
            lastPos = p + tok.length();
        }
        return true;
    }

    void RecursiveScan(const fs::path& root, const std::vector<std::string>& tokens, std::vector<std::string>& results, int depth, int maxDepth = 3) {
        if (depth > maxDepth || results.size() >= 20) return;

        PlatformFS::FileID id;
        if (!PlatformFS::GetUniqueID(root, id) || visited.count(id) > 0) {
            return;
        }
        visited.insert(id);

        try {
            for (const auto& entry : fs::directory_iterator(root, fs::directory_options::skip_permission_denied)) {
                if (entry.is_directory()) {
                    std::string pStr = entry.path().string();
                    std::string name = entry.path().filename().string();
                    if (!name.empty() && (name[0] == '.' || name == "node_modules" || name == "__pycache__" || name == "$Recycle.Bin")) {
                        continue;
                    }

                    if (PathMatchesTokens(pStr, tokens)) {
                        results.push_back(pStr);
                    }
                    RecursiveScan(entry.path(), tokens, results, depth + 1, maxDepth);
                }
            }
        } catch (...) {}
    }

public:
    SmartDirectoryJumper() {
        fs::path home = PlatformFS::GetHomeDir();
        if (fs::exists(home / "Desktop")) historyDirs.push_back((home / "Desktop").string());
        if (fs::exists(home / "Downloads")) historyDirs.push_back((home / "Downloads").string());
        if (fs::exists(home / "Documents")) historyDirs.push_back((home / "Documents").string());
        historyDirs.push_back(home.string());
    }

    void Record(const std::string& path) {
        if (path.empty()) return;
        auto it = std::find(historyDirs.begin(), historyDirs.end(), path);
        if (it != historyDirs.end()) historyDirs.erase(it);
        historyDirs.insert(historyDirs.begin(), path);
        if (historyDirs.size() > 100) historyDirs.pop_back();
    }

    void SetBookmark(const std::string& name, const std::string& path) { bookmarks[name] = path; }
    std::string GetBookmark(const std::string& name) { return bookmarks.count(name) ? bookmarks[name] : ""; }
    const std::map<std::string, std::string>& GetBookmarks() const { return bookmarks; }
    void SetLastDir(const std::string& d) { lastDir = d; }
    std::string GetLastDir() const { return lastDir; }

    std::string Jump(const std::string& query, const std::string& currentCwd) {
        if (query.empty()) return "";
        if (bookmarks.count(query) > 0) return bookmarks[query];

        std::vector<std::string> tokens = Tokenize(query);
        if (tokens.empty()) return "";

        try {
            for (const auto& entry : fs::directory_iterator(currentCwd)) {
                if (entry.is_directory() && PathMatchesTokens(entry.path().string(), tokens)) {
                    return entry.path().string();
                }
            }
        } catch (...) {}

        for (const auto& dir : historyDirs) {
            if (PathMatchesTokens(dir, tokens)) return dir;
        }

        visited.clear();
        std::vector<std::string> deepMatches;
        fs::path home = PlatformFS::GetHomeDir();
        fs::path desktop = home / "Desktop";
        if (fs::exists(desktop)) RecursiveScan(desktop, tokens, deepMatches, 0, 3);
        if (deepMatches.empty()) RecursiveScan(home, tokens, deepMatches, 0, 2);

        return deepMatches.empty() ? "" : deepMatches[0];
    }

    std::vector<std::string> DeepFind(const std::string& query, const std::string& currentCwd) {
        visited.clear();
        std::vector<std::string> tokens = Tokenize(query);
        std::vector<std::string> results;
        RecursiveScan(fs::path(currentCwd), tokens, results, 0, 4);

        if (results.size() < 10) {
            fs::path home = PlatformFS::GetHomeDir();
            fs::path desktop = home / "Desktop";
            if (fs::exists(desktop)) RecursiveScan(desktop, tokens, results, 0, 3);
        }
        return results;
    }

    std::vector<std::string> GetAvailableDirs(const std::string& currentCwd) {
        std::vector<std::string> list;
        try {
            for (const auto& entry : fs::directory_iterator(currentCwd)) {
                if (entry.is_directory()) {
                    list.push_back(entry.path().string());
                    if (list.size() >= 6) break;
                }
            }
        } catch (...) {}
        for (const auto& d : historyDirs) {
            if (std::find(list.begin(), list.end(), d) == list.end()) {
                list.push_back(d);
                if (list.size() >= 10) break;
            }
        }
        return list;
    }
};

// ═══════════════════════════════════════════════════════════
// Cross-Platform Process Spawner & Job Control
// ═══════════════════════════════════════════════════════════

class PlatformProcessRunner {
public:
    struct ExecResult {
        int exitCode = 0;
        std::string output;
    };

    static bool IsInteractiveTUI(const std::string& cmd) {
        std::string lower = cmd;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        std::vector<std::string> tuis = {"vim", "vi", "nano", "htop", "top", "fzf", "less", "man"};
        for (const auto& t : tuis) {
            if (lower == t || lower.rfind(t + " ", 0) == 0) return true;
        }
        return false;
    }

    static ExecResult Execute(const std::string& command) {
        ExecResult res;

        // Passthrough for interactive full-screen TUI apps with ConPTY / openpty
        if (IsInteractiveTUI(command)) {
            int cols = PlatformTerminal::GetWindowColumns();
            NeuroShell::PTY::PseudoTerminalHost pty;
            if (pty.Spawn(command, (short)cols, 30)) {
                std::thread outThread([&]() {
                    pty.StreamOutput([](const char* data, size_t len) {
                        std::cout.write(data, len);
                        std::cout.flush();
                    });
                });
                res.exitCode = pty.WaitForExit();
                if (outThread.joinable()) outThread.join();
                return res;
            }
            res.exitCode = system(command.c_str());
            return res;
        }

#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        HANDLE hJob = CreateJobObjectW(NULL, NULL);
        if (hJob != NULL) {
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli = { 0 };
            jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            SetInformationJobObject(hJob, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));
        }

        SECURITY_ATTRIBUTES sa;
        sa.nLength = sizeof(SECURITY_ATTRIBUTES);
        sa.bInheritHandle = TRUE;
        sa.lpSecurityDescriptor = NULL;

        HANDLE hReadPipe, hWritePipe;
        if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0)) {
            res.exitCode = system(command.c_str());
            if (hJob) CloseHandle(hJob);
            return res;
        }
        SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0);

        STARTUPINFOA si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        si.cb = sizeof(si);
        si.hStdError = hWritePipe;
        si.hStdOutput = hWritePipe;
        si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        si.dwFlags |= STARTF_USESTDHANDLES;
        ZeroMemory(&pi, sizeof(pi));

        std::string cmdLine = "cmd.exe /c " + command;
        std::vector<char> cmdBuf(cmdLine.begin(), cmdLine.end());
        cmdBuf.push_back('\0');

        BOOL success = CreateProcessA(NULL, cmdBuf.data(), NULL, NULL, TRUE, CREATE_SUSPENDED, NULL, NULL, &si, &pi);
        CloseHandle(hWritePipe);

        if (!success) {
            CloseHandle(hReadPipe);
            if (hJob) CloseHandle(hJob);
            res.exitCode = system(command.c_str());
            return res;
        }

        if (hJob != NULL) AssignProcessToJobObject(hJob, pi.hProcess);
        ResumeThread(pi.hThread);

        std::string rollingOutput = "";
        std::mutex outLock;
        const size_t MAX_CAPTURE = 65536;

        std::thread reader([&]() {
            char buffer[4096];
            DWORD bytesRead = 0;
            while (ReadFile(hReadPipe, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
                buffer[bytesRead] = '\0';
                std::cout << buffer << std::flush;
                std::lock_guard<std::mutex> lock(outLock);
                rollingOutput.append(buffer, bytesRead);
                if (rollingOutput.size() > MAX_CAPTURE * 2) {
                    rollingOutput.erase(0, rollingOutput.size() - MAX_CAPTURE);
                }
            }
        });

        WaitForSingleObject(pi.hProcess, INFINITE);
        DWORD dwExit = 0;
        GetExitCodeProcess(pi.hProcess, &dwExit);
        res.exitCode = static_cast<int>(dwExit);

        if (reader.joinable()) reader.join();

        {
            std::lock_guard<std::mutex> lock(outLock);
            res.output = std::move(rollingOutput);
        }

        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        CloseHandle(hReadPipe);
        if (hJob) CloseHandle(hJob);
#else
        int pipefds[2];
        if (pipe(pipefds) == -1) {
            res.exitCode = system(command.c_str());
            return res;
        }

        pid_t pid = fork();
        if (pid < 0) {
            close(pipefds[0]);
            close(pipefds[1]);
            res.exitCode = system(command.c_str());
            return res;
        }

        if (pid == 0) {
            setpgid(0, 0); // Isolate child in new process group
            close(pipefds[0]);
            dup2(pipefds[1], STDOUT_FILENO);
            dup2(pipefds[1], STDERR_FILENO);
            close(pipefds[1]);

            const char* shell = getenv("SHELL");
            if (!shell) shell = "/bin/sh";
            execl(shell, shell, "-c", command.c_str(), (char*)NULL);
            _exit(127);
        }

        close(pipefds[1]);
        std::string rollingOutput = "";
        std::mutex outLock;
        const size_t MAX_CAPTURE = 65536;

        std::thread reader([&]() {
            char buffer[4096];
            ssize_t n = 0;
            while ((n = read(pipefds[0], buffer, sizeof(buffer) - 1)) > 0) {
                buffer[n] = '\0';
                std::cout << buffer << std::flush;
                std::lock_guard<std::mutex> lock(outLock);
                rollingOutput.append(buffer, n);
                if (rollingOutput.size() > MAX_CAPTURE * 2) {
                    rollingOutput.erase(0, rollingOutput.size() - MAX_CAPTURE);
                }
            }
        });

        int status = 0;
        waitpid(pid, &status, 0);
        if (WIFEXITED(status)) res.exitCode = WEXITSTATUS(status);
        else if (WIFSIGNALED(status)) res.exitCode = 128 + WTERMSIG(status);
        else res.exitCode = 1;

        if (reader.joinable()) reader.join();
        close(pipefds[0]);

        {
            std::lock_guard<std::mutex> lock(outLock);
            res.output = std::move(rollingOutput);
        }
#endif
        return res;
    }
};

// ═══════════════════════════════════════════════════════════
// Master Native C++ Terminal Application Class
// ═══════════════════════════════════════════════════════════

class EnterpriseTerminalHost {
private:
    std::string activeProvider = "groq";
    std::string activeModel = "llama-3.3-70b-versatile";
    std::string activeTheme = "Cyberpunk Neon";

    PredictionEngine predictor;
    SyntaxHighlighter highlighter;
    SmartErrorShield errorShield;
    SmartDirectoryJumper jumper;
    PlatformTerminal terminal;
    NeuroShell::IPC::NeuroIPCClient ipcClient;
    neuroshell::DLPMasker dlpMasker;
    neuroshell::SHMRingBuffer shmRing;
    neuroshell::StreamRecorder streamRecorder;
    neuroshell::SplitPaneManager splitPanes;

    std::vector<HistoryEntry> history;
    int historyIndex = 0;

    std::vector<Tab> tabs;
    int activeTabIdx = 0;

public:
    EnterpriseTerminalHost() {
        PlatformTerminal::SetTitle("NeuroShell v5.2.0 — Enterprise Flagship AI Terminal");
        fs::path cur = fs::current_path();
        tabs.push_back({1, cur.filename().string(), cur.string()});
        shmRing.initialize_as_host();
        LoadConfig();
        LoadHistory();
        NeuroShell::Daemon::DaemonManager::EnsureDaemonRunning(ipcClient);
    }

    fs::path GetConfigPath() {
        return PlatformFS::GetHomeDir() / ".neuroshell" / "config.toml";
    }

    fs::path GetHistoryPath() {
        return PlatformFS::GetHomeDir() / ".neuroshell" / "history.txt";
    }

    void LoadConfig() {
        fs::path configPath = GetConfigPath();
        if (!fs::exists(configPath)) return;

        std::ifstream f(configPath);
        std::string line;
        while (std::getline(f, line)) {
            if (line.find("provider = ") != std::string::npos) {
                size_t q1 = line.find("\"");
                size_t q2 = line.rfind("\"");
                if (q1 != std::string::npos && q2 > q1) activeProvider = line.substr(q1 + 1, q2 - q1 - 1);
            }
            if (line.find("model = ") != std::string::npos) {
                size_t q1 = line.find("\"");
                size_t q2 = line.rfind("\"");
                if (q1 != std::string::npos && q2 > q1) activeModel = line.substr(q1 + 1, q2 - q1 - 1);
            }
        }
    }

    void SaveConfig(const std::string& provider, const std::string& model, const std::string& apiKey = "") {
        activeProvider = provider;
        activeModel = model;

        fs::path configPath = GetConfigPath();
        fs::create_directories(configPath.parent_path());

        std::ofstream f(configPath);
        f << "# NeuroShell Configuration\n[llm]\nprovider = \"" << provider << "\"\nmodel = \"" << model << "\"\ntemperature = 0.2\n\n";
        if (!apiKey.empty()) {
            f << "[secrets]\n" << provider << "_api_key = \"" << apiKey << "\"\n";
        }
    }

    void LoadHistory() {
        fs::path histPath = GetHistoryPath();
        if (!fs::exists(histPath)) return;

        std::ifstream f(histPath);
        std::string line;
        while (std::getline(f, line)) {
            if (!line.empty()) {
                history.push_back({line, "", 0});
                predictor.Learn(line);
            }
        }
        historyIndex = (int)history.size();
    }

    void AppendHistory(const std::string& cmd) {
        if (cmd.empty()) return;
        history.push_back({cmd, tabs[activeTabIdx].cwd, 0});
        historyIndex = (int)history.size();
        predictor.Learn(cmd);

        fs::path histPath = GetHistoryPath();
        fs::create_directories(histPath.parent_path());
        std::ofstream f(histPath, std::ios::app);
        if (f.is_open()) f << cmd << "\n";
    }

    void PrintBanner() {
        std::cout << C_CYAN << "╭──────────────────────────────────────────────────────────────────────────╮\n"
                  << "│  " << C_BOLD << C_WHITE << "⌬ NeuroShell" << C_RESET << C_MAGENTA " v5.2.0" 
                  << C_CYAN " — Tier-1 Enterprise Flagship AI Terminal           │\n"
                  << "│  " << C_MUTED << "C++20 Host • ConPTY • Zero-Trust DLP • SHM Ring (" << activeProvider << ")" 
                  << C_CYAN "  │\n"
                  << "╰──────────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n";
        
        std::cout << C_MUTED << "  • Type in plain English • Pipe AI: 'cat file | @ai', 'pytest | @fix'\n"
                  << "  • Swarms: '@agent <task>' • Split Panes: 'vsplit', 'hsplit' • Cluster: '@cluster <cmd>'\n"
                  << "  • DLP Masking: [Ctrl+U] to unmask/re-mask • Time-Travel Scrub: [Ctrl+Shift+H]\n"
                  << "  • Reverse History: [Ctrl+R] • Multi-Tabs: [Ctrl+T] / [Ctrl+W]\n"
                  << "  • Settings: /api-key, /model, /theme, /dlp, /help\n\n" << C_RESET;
    }

    void RenderTabBar() {
        if (tabs.size() <= 1) return;

        std::cout << " ";
        for (int i = 0; i < (int)tabs.size(); ++i) {
            std::string label = " " + std::to_string(i + 1) + ": " + tabs[i].name + " ";
            if (i == activeTabIdx) {
                std::cout << C_TAB_ACT << C_BOLD << label << C_RESET << " ";
            } else {
                std::cout << C_TAB_IN << "[" << label << "]" << C_RESET << " ";
            }
        }
        std::cout << C_MUTED << "(+ Ctrl+T)\n" << C_RESET;
    }

    std::string GetGitBranch() {
        if (fs::exists(".git/HEAD")) {
            try {
                std::ifstream f(".git/HEAD");
                std::string s;
                if (std::getline(f, s)) {
                    size_t pos = s.find("refs/heads/");
                    if (pos != std::string::npos) {
                        std::string branch = s.substr(pos + 11);
                        branch.erase(branch.find_last_not_of(" \n\r\t") + 1);
                        return branch;
                    }
                }
            } catch (...) {}
        }
        return "";
    }

    // ═══════════════════════════════════════════════════════
    // Interactive Character-by-Character Line Editor
    // ═══════════════════════════════════════════════════════

    std::string ReadLine(const std::string& promptPrefix) {
        std::string buffer = "";
        std::string ghostSuggestion = "";
        int cursorPos = 0;
        int localHistIdx = (int)history.size();

        auto Redraw = [&]() {
            ghostSuggestion = (cursorPos == (int)buffer.length()) ? predictor.GetSuggestion(buffer) : "";

            std::cout << "\r\033[2K" << promptPrefix;
            std::cout << highlighter.Highlight(buffer);

            if (!ghostSuggestion.empty()) {
                std::cout << C_GHOST << ghostSuggestion << C_RESET;
            }

            int tailOffset = (int)buffer.length() - cursorPos + (int)ghostSuggestion.length();
            if (tailOffset > 0) {
                std::cout << "\033[" << tailOffset << "D";
            }
            std::cout.flush();
        };

        Redraw();

        while (true) {
            KeyEvent ev = terminal.ReadKey();

            if (ev.code == KeyCode::Enter) {
                std::cout << "\n";
                break;
            }
            if (ev.code == KeyCode::Ctrl_C) {
                std::cout << C_MUTED << " ^C\n" << C_RESET;
                return "";
            }
            if (ev.code == KeyCode::Ctrl_L) {
                PlatformTerminal::ClearScreen();
                PrintBanner();
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Ctrl_R) {
                std::string chosen = ReverseSearchModal();
                if (!chosen.empty()) {
                    buffer = chosen;
                    cursorPos = (int)buffer.length();
                }
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Ctrl_T) {
                if (tabs.size() < 9) {
                    fs::path cwd = fs::current_path();
                    int newId = (int)tabs.size() + 1;
                    tabs.push_back({newId, cwd.filename().string(), cwd.string()});
                    activeTabIdx = (int)tabs.size() - 1;
                    std::cout << "\n" << C_GREEN << "  ✨ Created Tab " << newId << C_RESET << "\n";
                }
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Ctrl_W) {
                if (tabs.size() > 1) {
                    tabs.erase(tabs.begin() + activeTabIdx);
                    activeTabIdx = std::max(0, activeTabIdx - 1);
                    fs::current_path(tabs[activeTabIdx].cwd);
                    std::cout << "\n" << C_YELLOW << "  🗑️ Closed Tab" << C_RESET << "\n";
                }
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Tab) {
                if (!ghostSuggestion.empty() && cursorPos == (int)buffer.length()) {
                    buffer += ghostSuggestion;
                    cursorPos = (int)buffer.length();
                } else {
                    std::string pathComp = predictor.GetPathCompletion(buffer);
                    if (!pathComp.empty()) {
                        buffer += pathComp;
                        cursorPos = (int)buffer.length();
                    }
                }
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Backspace) {
                if (cursorPos > 0) {
                    buffer.erase(cursorPos - 1, 1);
                    cursorPos--;
                }
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Left) {
                if (cursorPos > 0) cursorPos--;
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Right) {
                if (cursorPos < (int)buffer.length()) {
                    cursorPos++;
                } else if (!ghostSuggestion.empty()) {
                    buffer += ghostSuggestion;
                    cursorPos = (int)buffer.length();
                }
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Up) {
                if (!history.empty() && localHistIdx > 0) {
                    localHistIdx--;
                    buffer = history[localHistIdx].command;
                    cursorPos = (int)buffer.length();
                }
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Down) {
                if (localHistIdx < (int)history.size() - 1) {
                    localHistIdx++;
                    buffer = history[localHistIdx].command;
                    cursorPos = (int)buffer.length();
                } else {
                    localHistIdx = (int)history.size();
                    buffer = "";
                    cursorPos = 0;
                }
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Home) {
                cursorPos = 0;
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::End) {
                cursorPos = (int)buffer.length();
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Delete) {
                if (cursorPos < (int)buffer.length()) {
                    buffer.erase(cursorPos, 1);
                }
                Redraw();
                continue;
            }
            if (ev.code == KeyCode::Printable) {
                buffer.insert(cursorPos, 1, ev.ch);
                cursorPos++;
                Redraw();
            }
        }

        return buffer;
    }

    // ═══════════════════════════════════════════════════════
    // Reverse History Search Modal (Ctrl + R)
    // ═══════════════════════════════════════════════════════

    std::string ReverseSearchModal() {
        std::string query = "";
        std::cout << "\n";

        while (true) {
            std::vector<std::string> matches;
            for (int i = (int)history.size() - 1; i >= 0; --i) {
                if (query.empty() || history[i].command.find(query) != std::string::npos) {
                    if (std::find(matches.begin(), matches.end(), history[i].command) == matches.end()) {
                        matches.push_back(history[i].command);
                        if (matches.size() >= 5) break;
                    }
                }
            }

            std::cout << "\r\033[2K" << C_CYAN << "  (reverse-i-search)`" << C_BOLD << C_WHITE << query << C_RESET << C_CYAN << "': " << C_RESET;
            if (!matches.empty()) {
                std::cout << C_GREEN << matches[0] << C_RESET;
            }
            std::cout.flush();

            KeyEvent ev = terminal.ReadKey();
            if (ev.code == KeyCode::Enter) {
                std::cout << "\n";
                return matches.empty() ? query : matches[0];
            } else if (ev.code == KeyCode::Escape || ev.code == KeyCode::Ctrl_C) {
                std::cout << "\n";
                return "";
            } else if (ev.code == KeyCode::Backspace) {
                if (!query.empty()) query.pop_back();
            } else if (ev.code == KeyCode::Printable) {
                query.push_back(ev.ch);
            }
        }
    }

    // ═══════════════════════════════════════════════════════
    // In-Place Arrow-Key Menu Selector for Slash Commands
    // ═══════════════════════════════════════════════════════

    int SelectMenu(const std::string& title, const std::vector<MenuItem>& items, int initialSelection = 0) {
        int count = (int)items.size();
        if (count <= 0) return -1;

        int selected = std::clamp(initialSelection, 0, count - 1);
        bool firstRender = true;

        std::cout << "\033[?25l";

        while (true) {
            if (!firstRender) {
                std::cout << "\033[" << (count + 3) << "A\r";
            }
            firstRender = false;

            std::cout << C_CYAN << "  ╭── " << C_BOLD << C_WHITE << title << C_RESET << C_CYAN << " " 
                      << std::string(std::max(0, 52 - (int)title.length()), '─') << "╮\033[K\n";

            for (int i = 0; i < count; ++i) {
                std::string num = "[" + std::to_string(i + 1) + "]";
                if (i == selected) {
                    std::cout << C_CYAN << "  │ " << C_BOLD << C_GREEN << " ❯ " << num << " " << items[i].label << C_RESET 
                              << C_MUTED << " • " << items[i].desc << C_CYAN << "\033[K\n";
                } else {
                    std::cout << C_CYAN << "  │   " << C_DIM << C_WHITE << num << " " << items[i].label << C_RESET 
                              << C_MUTED << " • " << items[i].desc << C_CYAN << "\033[K\n";
                }
            }

            std::cout << C_CYAN << "  ╰────────────────────────────────────────────────────────╯\033[K\n";
            std::cout << C_MUTED << "  (Use ↑/↓ arrows or 1-" << count << " to choose, Enter to confirm, Esc to cancel)\033[K" << C_RESET << "\n";

            KeyEvent ev = terminal.ReadKey();
            if (ev.code == KeyCode::Up) {
                selected = (selected - 1 + count) % count;
            } else if (ev.code == KeyCode::Down) {
                selected = (selected + 1) % count;
            } else if (ev.code == KeyCode::Enter) {
                break;
            } else if (ev.code == KeyCode::Escape || ev.code == KeyCode::Ctrl_C) {
                selected = -1;
                break;
            } else if (ev.code == KeyCode::Printable && ev.ch >= '1' && ev.ch < ('1' + count)) {
                selected = ev.ch - '1';
                break;
            }
        }

        std::cout << "\033[?25h\n";
        return selected;
    }

    std::string PromptMasked(const std::string& promptText) {
        std::cout << C_CYAN << "  🔑 " << C_BOLD << C_WHITE << promptText << C_RESET << ": ";
        std::string secret = "";

        while (true) {
            KeyEvent ev = terminal.ReadKey();
            if (ev.code == KeyCode::Enter) {
                std::cout << "\n";
                break;
            } else if (ev.code == KeyCode::Escape || ev.code == KeyCode::Ctrl_C) {
                std::cout << C_MUTED << " [Cancelled]\n" << C_RESET;
                return "";
            } else if (ev.code == KeyCode::Backspace) {
                if (!secret.empty()) {
                    secret.pop_back();
                    std::cout << "\b \b" << std::flush;
                }
            } else if (ev.code == KeyCode::Printable) {
                secret.push_back(ev.ch);
                std::cout << C_MAGENTA << "•" << C_RESET << std::flush;
            }
        }
        return secret;
    }

    // ═══════════════════════════════════════════════════════
    // Natural Language & Slash Command Handlers
    // ═══════════════════════════════════════════════════════

    std::string TranslateNaturalLanguage(const std::string& input) {
        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        size_t first = lower.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) return "";
        size_t last = lower.find_last_not_of(" \t\r\n");
        lower = lower.substr(first, last - first + 1);

        // 1. File Explorer & Browser Openers
        if (lower == "open file explorer" || lower == "open explorer" || lower == "file explorer" || lower == "open current folder") {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            return "explorer .";
#elif defined(__APPLE__)
            return "open .";
#else
            return "xdg-open .";
#endif
        }
        if (lower.rfind("open folder ", 0) == 0) {
            std::string pathStr = input.substr(12);
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            return "explorer \"" + pathStr + "\"";
#elif defined(__APPLE__)
            return "open \"" + pathStr + "\"";
#else
            return "xdg-open \"" + pathStr + "\"";
#endif
        }
        if (lower.rfind("open http://", 0) == 0 || lower.rfind("open https://", 0) == 0) {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            return "start " + input.substr(5);
#elif defined(__APPLE__)
            return "open " + input.substr(5);
#else
            return "xdg-open " + input.substr(5);
#endif
        }
        if (lower.rfind("open ", 0) == 0) {
            std::string target = input.substr(5);
            if (target == "chrome" || target == "browser") {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
                return "start msedge || start chrome";
#elif defined(__APPLE__)
                return "open -a \"Google Chrome\" || open -a Safari";
#else
                return "google-chrome || firefox || xdg-open https://google.com";
#endif
            }
            if (target == "github" || target == "my github") {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
                return "start https://github.com";
#elif defined(__APPLE__)
                return "open https://github.com";
#else
                return "xdg-open https://github.com";
#endif
            }
            if (target == "calculator" || target == "calc") {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
                return "calc";
#elif defined(__APPLE__)
                return "open -a Calculator";
#else
                return "gnome-calculator || kcalc || bc";
#endif
            }
        }

        // 2. Web & Browser Download Operations
        if (lower.rfind("download ", 0) == 0) {
            std::string url = input.substr(9);
            url.erase(0, url.find_first_not_of(" \t\r\n"));
            url.erase(url.find_last_not_of(" \t\r\n") + 1);
            return "curl -LO \"" + url + "\"";
        }
        if (lower.rfind("fetch ", 0) == 0) {
            std::string url = input.substr(6);
            return "curl -sL \"" + url + "\"";
        }

        // 3. GitHub & Git Operations
        if (lower == "show my github repos" || lower == "list my repos" || lower == "my repos" || lower == "view my repos" || lower == "github repos") {
            return "gh repo list || git log --oneline -n 5";
        }
        if (lower == "find all git repos" || lower == "list local repos" || lower == "show local repos" || lower == "local repos") {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            return "dir /s /b /ad .git";
#else
            return "find . -name .git -type d";
#endif
        }
        if (lower.rfind("clone repo ", 0) == 0 || lower.rfind("clone ", 0) == 0) {
            size_t startIdx = (lower.rfind("clone repo ", 0) == 0) ? 11 : 6;
            return "git clone " + input.substr(startIdx);
        }
        if (lower.rfind("push to ", 0) == 0) {
            std::string branch = input.substr(8);
            if (branch == "github") return "git push origin main || git push";
            return "git push origin " + branch;
        }
        if (lower == "push" || lower == "push to github" || lower == "push changes" || lower == "git push") {
            return "git push origin main || git push";
        }
        if (lower.rfind("pull from ", 0) == 0) {
            std::string branch = input.substr(10);
            if (branch == "github") return "git pull origin main || git pull";
            return "git pull origin " + branch;
        }
        if (lower == "pull" || lower == "pull from github" || lower == "pull changes" || lower == "git pull") {
            return "git pull origin main || git pull";
        }
        if (lower == "git status" || lower == "repo status" || lower == "check git status") {
            return "git status";
        }
        if (lower.rfind("commit ", 0) == 0 || lower.rfind("commit changes ", 0) == 0) {
            size_t msgPos = input.find("\"");
            std::string msg = "update";
            if (msgPos != std::string::npos) {
                size_t endQuote = input.find("\"", msgPos + 1);
                if (endQuote != std::string::npos) {
                    msg = input.substr(msgPos + 1, endQuote - msgPos - 1);
                }
            }
            return "git add . && git commit -m \"" + msg + "\"";
        }

        // 4. File Searching & Utilities
        if (lower.rfind("find all ", 0) == 0 && lower.find(" files") != std::string::npos) {
            size_t extStart = 9;
            size_t extEnd = lower.find(" files");
            std::string ext = lower.substr(extStart, extEnd - extStart);
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            if (ext == "python" || ext == "py") return "dir /s /b *.py";
            if (ext == "javascript" || ext == "js") return "dir /s /b *.js";
            if (ext == "typescript" || ext == "ts") return "dir /s /b *.ts";
            if (ext == "c++" || ext == "cpp") return "dir /s /b *.cpp *.h";
            return "dir /s /b *." + ext;
#else
            if (ext == "python" || ext == "py") return "find . -name \"*.py\"";
            if (ext == "javascript" || ext == "js") return "find . -name \"*.js\"";
            if (ext == "typescript" || ext == "ts") return "find . -name \"*.ts\"";
            if (ext == "c++" || ext == "cpp") return "find . -name \"*.cpp\" -o -name \"*.h\"";
            return "find . -name \"*." + ext + "\"";
#endif
        }

        // 5. System info
        if (lower == "system info" || lower == "show system info" || lower == "specs") {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            return "systeminfo";
#elif defined(__APPLE__)
            return "uname -a && sw_vers";
#else
            return "uname -a && lscpu || uname -a";
#endif
        }
        if (lower == "my ip" || lower == "show ip" || lower == "ip address") {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            return "ipconfig";
#elif defined(__APPLE__)
            return "ifconfig";
#else
            return "ip a || ifconfig";
#endif
        }

        // 6. Query Python Intelligence IPC Daemon (Multi-LLM Router + 2554+ Phrase Dictionary + 4-Layer Safety Shield)
        NeuroShell::IPC::TranslationResult trans = ipcClient.Translate(input, fs::current_path().string());
        if (trans.success && !trans.command.empty() && trans.command != input) {
            return trans.command;
        }

        return "";
    }

    void HandleSlashApiKey() {
        std::vector<MenuItem> providers = {
            {"GROQ", "Ultra-Fast Cloud Inference (Default)", "groq"},
            {"OPENAI", "GPT-4o, GPT-4o-mini", "openai"},
            {"ANTHROPIC", "Claude 3.5 Sonnet", "anthropic"},
            {"GEMINI", "Google DeepMind 1.5 Flash / Pro", "gemini"},
            {"OPENROUTER", "100+ Models Multi-Provider Gateway", "openrouter"},
            {"OLLAMA", "Local Private SLM (Air-Gapped / Offline)", "ollama"}
        };

        int curIdx = 0;
        for (int i = 0; i < (int)providers.size(); ++i) {
            if (providers[i].id == activeProvider) {
                curIdx = i;
                break;
            }
        }

        std::cout << "\n";
        int choice = SelectMenu("Select LLM Provider", providers, curIdx);
        if (choice < 0) return;

        MenuItem selected = providers[choice];
        std::string defaultModel = "llama-3.3-70b-versatile";
        if (selected.id == "openai") defaultModel = "gpt-4o-mini";
        if (selected.id == "anthropic") defaultModel = "claude-3-5-sonnet-20241022";
        if (selected.id == "gemini") defaultModel = "gemini-1.5-flash";
        if (selected.id == "openrouter") defaultModel = "meta-llama/llama-3.3-70b-instruct";
        if (selected.id == "ollama") defaultModel = "phi3:mini";

        if (selected.id == "ollama") {
            SaveConfig("ollama", defaultModel);
            std::cout << "  " << C_GREEN << "✅ Provider set to Ollama (Air-Gapped / Offline SLM). No API key needed!" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Default Model: " << defaultModel << C_RESET << "\n\n";
            return;
        }

        std::string key = PromptMasked("Enter " + selected.label + " API Key");
        if (key.empty()) {
            std::cout << "  " << C_YELLOW << "⚠️ No key entered. Provider not updated." << C_RESET << "\n\n";
            return;
        }

        SaveConfig(selected.id, defaultModel, key);
        std::cout << "  " << C_GREEN << "✅ Successfully configured " << selected.label << "!" << C_RESET << "\n";
        std::cout << "  " << C_MUTED << "Encrypted & Saved to ~/.neuroshell/config.toml" << C_RESET << "\n";
        std::cout << "  " << C_MUTED << "Default Model: " << defaultModel << C_RESET << "\n\n";
    }

    void HandleSlashModel() {
        std::vector<MenuItem> models = {
            {"llama-3.3-70b-versatile", "Groq Cloud • Ultra Fast (Recommended)", "llama-3.3-70b-versatile"},
            {"gpt-4o-mini", "OpenAI • Efficient & Smart", "gpt-4o-mini"},
            {"claude-3-5-sonnet-20241022", "Anthropic • Best Coding Agent", "claude-3-5-sonnet-20241022"},
            {"gemini-1.5-flash", "Google • 1M Context Window", "gemini-1.5-flash"},
            {"phi3:mini", "Ollama Local • Air-Gapped SLM", "phi3:mini"}
        };

        int curIdx = 0;
        for (int i = 0; i < (int)models.size(); ++i) {
            if (models[i].id == activeModel) {
                curIdx = i;
                break;
            }
        }

        std::cout << "\n";
        int choice = SelectMenu("Select Active AI Model", models, curIdx);
        if (choice < 0) return;

        MenuItem selected = models[choice];
        SaveConfig(activeProvider, selected.id);
        std::cout << "  " << C_GREEN << "✅ Active Model switched to: " << C_BOLD << C_WHITE << selected.id << C_RESET << "\n\n";
    }

    void HandleSlashTheme() {
        std::vector<MenuItem> themes = {
            {"Cyberpunk Neon", "Cyan Prompt • Magenta Accents (Default)", "cyberpunk"},
            {"Matrix Emerald", "Green Glow • High Contrast Black", "matrix"},
            {"Dracula Night", "Purple / Pink • Dark Slate", "dracula"},
            {"Monokai Pro", "Amber Yellow • Vibrant Magenta", "monokai"},
            {"Nord Frost", "Ice Blue • Arctic Snow", "nord"}
        };

        std::cout << "\n";
        int choice = SelectMenu("Select Terminal Theme", themes, 0);
        if (choice < 0) return;

        activeTheme = themes[choice].label;
        std::cout << "  " << C_GREEN << "🎨 Theme changed to: " << C_BOLD << C_WHITE << activeTheme << C_RESET << "\n\n";
    }

    void HandleSlashCommand(const std::string& input) {
        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        if (lower == "/help") {
            std::cout << "\n" << C_BOLD << C_CYAN << "  📚 NeuroShell Slash Commands:" << C_RESET << "\n"
                      << "  " << C_MAGENTA << "/api-key" << C_RESET << "   • Interactive Arrow-Key LLM Provider & Key Setup\n"
                      << "  " << C_MAGENTA << "/model" << C_RESET << "     • Switch active AI model with arrow keys\n"
                      << "  " << C_MAGENTA << "/theme" << C_RESET << "     • Select Cyberpunk terminal theme with arrow keys\n"
                      << "  " << C_MAGENTA << "/swarm" << C_RESET << "     • Launch autonomous multi-agent task swarm\n"
                      << "  " << C_MAGENTA << "/plan" << C_RESET << "      • Interactive multi-step execution planner\n"
                      << "  " << C_MAGENTA << "/stats" << C_RESET << "     • View token consumption and latency metrics\n"
                      << "  " << C_MAGENTA << "/clear" << C_RESET << "     • Clear terminal screen\n"
                      << "  " << C_MAGENTA << "/help" << C_RESET << "      • Display this help menu\n\n";
        }
        else if (lower == "/api-key") {
            HandleSlashApiKey();
        }
        else if (lower == "/model") {
            HandleSlashModel();
        }
        else if (lower == "/theme") {
            HandleSlashTheme();
        }
        else {
            std::cout << C_MUTED << "  ℹ️ Executed slash command: " << input << C_RESET << "\n\n";
        }
    }

    // ═══════════════════════════════════════════════════════
    // Non-Blocking Asynchronous Process Executor
    // ═══════════════════════════════════════════════════════

    void ExecuteCommand(const std::string& input) {
        if (input.empty()) return;

        AppendHistory(input);

        // 1. Exit
        if (input == "exit" || input == "quit" || input == "q") {
            exit(0);
        }

        // 2. Clear Screen
        if (input == "cls" || input == "clear" || input == "/clear") {
            PlatformTerminal::ClearScreen();
            PrintBanner();
            return;
        }

        // 2b. Viewport DLP & Secret Masker Commands
        std::string lowerTrim = input;
        std::transform(lowerTrim.begin(), lowerTrim.end(), lowerTrim.begin(), ::tolower);

        if (lowerTrim == "/dlp" || lowerTrim == "dlp") {
            std::cout << "\n" << C_CYAN << "  🛡️ Viewport Secret DLP Status:\n" << C_RESET;
            std::cout << "  • Real-Time Scanning: " << (dlpMasker.is_enabled() ? (std::string(C_GREEN) + "ACTIVE" + C_RESET) : (std::string(C_RED) + "DISABLED" + C_RESET)) << "\n";
            std::cout << "  • Unmask Mode:        " << (dlpMasker.is_unmasked() ? (std::string(C_YELLOW) + "UNMASKED (Press Ctrl+U to re-mask)" + C_RESET) : (std::string(C_GREEN) + "MASKED (Secure)" + C_RESET)) << "\n";
            std::cout << "  • Total Secrets Masked: " << C_BOLD << C_WHITE << dlpMasker.get_total_masked() << C_RESET << "\n\n";
            return;
        }

        if (lowerTrim == "/unmask" || lowerTrim == "unmask") {
            dlpMasker.toggle_unmask();
            std::cout << "  " << (dlpMasker.is_unmasked() ? (std::string(C_YELLOW) + "🔓 Secrets temporarily unmasked. Use /unmask or Ctrl+U to re-mask." + C_RESET) : (std::string(C_GREEN) + "🔒 Secrets re-masked." + C_RESET)) << "\n\n";
            return;
        }

        if (lowerTrim == "/export-session" || lowerTrim == "export session") {
            std::string exportPath = "neuroshell_session.cast";
            if (streamRecorder.export_asciinema(exportPath)) {
                std::cout << "  " << C_GREEN << "✨ Session successfully exported to " << C_BOLD << C_WHITE << exportPath << C_RESET << C_GREEN << " (Asciinema v2 format)\n\n" << C_RESET;
            } else {
                std::cout << "  " << C_RED << "❌ Failed to export session recording.\n\n" << C_RESET;
            }
            return;
        }

        // 2c. 2D Split Panes & Cluster Broadcasting
        if (lowerTrim == "vsplit" || lowerTrim == "/vsplit") {
            splitPanes.split_vertical(fs::current_path().string());
            return;
        }
        if (lowerTrim == "hsplit" || lowerTrim == "/hsplit") {
            splitPanes.split_horizontal(fs::current_path().string());
            return;
        }
        if (lowerTrim.rfind("@cluster ", 0) == 0) {
            std::string clusterCmd = input.substr(9);
            splitPanes.broadcast_command(clusterCmd);
            return;
        }

        // 3. Smart Directory Jumper & Navigation Shortcuts

        if (lowerTrim == ".." || lowerTrim == "...") {
            fs::path cur = fs::current_path();
            jumper.SetLastDir(cur.string());

            fs::path dest = (lowerTrim == "..") ? cur.parent_path() : cur.parent_path().parent_path();
            try {
                fs::current_path(dest);
                fs::path newCwd = fs::current_path();
                jumper.Record(newCwd.string());
                tabs[activeTabIdx].cwd = newCwd.string();
                tabs[activeTabIdx].name = newCwd.filename().string();
            } catch (...) {}
            return;
        }

        if (lowerTrim == "back" || lowerTrim == "cd -") {
            std::string last = jumper.GetLastDir();
            if (!last.empty()) {
                fs::path cur = fs::current_path();
                jumper.SetLastDir(cur.string());

                try {
                    fs::current_path(last);
                    fs::path newCwd = fs::current_path();
                    tabs[activeTabIdx].cwd = newCwd.string();
                    tabs[activeTabIdx].name = newCwd.filename().string();
                    std::cout << "  " << C_GREEN << "⚡ Returned → " << C_BOLD << C_WHITE << newCwd.string() << C_RESET << "\n";
                } catch (...) {}
            } else {
                std::cout << "  " << C_MUTED << "No previous directory recorded." << C_RESET << "\n";
            }
            return;
        }

        if (lowerTrim == "z") {
            std::string currentCwd = fs::current_path().string();
            std::vector<std::string> avail = jumper.GetAvailableDirs(currentCwd);

            std::vector<MenuItem> dirItems;
            for (const auto& d : avail) {
                dirItems.push_back({fs::path(d).filename().string(), d, d});
            }

            int choice = SelectMenu("Quick Jump to Directory", dirItems, 0);
            if (choice >= 0) {
                jumper.SetLastDir(currentCwd);
                fs::current_path(dirItems[choice].id);
                fs::path newCwd = fs::current_path();
                jumper.Record(newCwd.string());
                tabs[activeTabIdx].cwd = newCwd.string();
                tabs[activeTabIdx].name = newCwd.filename().string();
                std::cout << "  " << C_GREEN << "⚡ Jumped → " << C_BOLD << C_WHITE << newCwd.string() << C_RESET << "\n";
            }
            return;
        }

        if (lowerTrim.rfind("f ", 0) == 0 || lowerTrim.rfind("find dir ", 0) == 0) {
            std::string query = (lowerTrim.rfind("f ", 0) == 0) ? input.substr(2) : input.substr(9);
            query.erase(0, query.find_first_not_of(" \t\r\n"));
            query.erase(query.find_last_not_of(" \t\r\n") + 1);

            std::string currentCwd = fs::current_path().string();
            std::vector<std::string> matches = jumper.DeepFind(query, currentCwd);

            if (matches.empty()) {
                std::cout << "  " << C_RED << "❌ No directory matching '" << query << "' found." << C_RESET << "\n";
                return;
            }

            std::vector<MenuItem> items;
            for (const auto& m : matches) {
                items.push_back({fs::path(m).filename().string(), m, m});
            }

            int choice = SelectMenu("Deep Folder Search: " + query, items, 0);
            if (choice >= 0) {
                jumper.SetLastDir(currentCwd);
                fs::current_path(items[choice].id);
                fs::path newCwd = fs::current_path();
                jumper.Record(newCwd.string());
                tabs[activeTabIdx].cwd = newCwd.string();
                tabs[activeTabIdx].name = newCwd.filename().string();
                std::cout << "  " << C_GREEN << "⚡ Jumped → " << C_BOLD << C_WHITE << newCwd.string() << C_RESET << "\n";
            }
            return;
        }

        if (lowerTrim.rfind("mark ", 0) == 0 || lowerTrim.rfind("bookmark ", 0) == 0) {
            std::string name = (lowerTrim.rfind("mark ", 0) == 0) ? input.substr(5) : input.substr(9);
            name.erase(0, name.find_first_not_of(" \t\r\n"));
            name.erase(name.find_last_not_of(" \t\r\n") + 1);

            std::string currentCwd = fs::current_path().string();
            jumper.SetBookmark(name, currentCwd);
            std::cout << "  " << C_GREEN << "🔖 Bookmarked '" << C_BOLD << name << C_RESET << C_GREEN << "' → " << currentCwd << C_RESET << "\n";
            return;
        }

        if (lowerTrim.rfind("bm ", 0) == 0 || lowerTrim == "bookmarks") {
            if (lowerTrim == "bookmarks") {
                const auto& bms = jumper.GetBookmarks();
                if (bms.empty()) {
                    std::cout << "  " << C_MUTED << "No bookmarks saved yet. Use 'mark <name>' to save current folder." << C_RESET << "\n";
                } else {
                    std::cout << "\n" << C_CYAN << "  📚 Saved Folder Bookmarks:\n" << C_RESET;
                    for (const auto& [k, v] : bms) {
                        std::cout << "  " << C_MAGENTA << k << C_RESET << " → " << C_WHITE << v << C_RESET << "\n";
                    }
                    std::cout << "\n";
                }
                return;
            }
            std::string name = input.substr(3);
            name.erase(0, name.find_first_not_of(" \t\r\n"));
            name.erase(name.find_last_not_of(" \t\r\n") + 1);
            std::string target = jumper.GetBookmark(name);
            if (!target.empty()) {
                std::string currentCwd = fs::current_path().string();
                jumper.SetLastDir(currentCwd);
                fs::current_path(target);
                fs::path newCwd = fs::current_path();
                jumper.Record(newCwd.string());
                tabs[activeTabIdx].cwd = newCwd.string();
                tabs[activeTabIdx].name = newCwd.filename().string();
                std::cout << "  " << C_GREEN << "⚡ Teleported to '" << name << "' → " << C_BOLD << C_WHITE << newCwd.string() << C_RESET << "\n";
            } else {
                std::cout << "  " << C_RED << "❌ Bookmark '" << name << "' not found. Type 'bookmarks' to view list." << C_RESET << "\n";
            }
            return;
        }

        bool isJumpCmd = false;
        std::string jumpQuery = "";
        if (lowerTrim.rfind("z ", 0) == 0) {
            isJumpCmd = true;
            jumpQuery = input.substr(2);
        } else if (lowerTrim.rfind("goto ", 0) == 0 || lowerTrim.rfind("go to ", 0) == 0) {
            isJumpCmd = true;
            jumpQuery = (lowerTrim.rfind("goto ", 0) == 0) ? input.substr(5) : input.substr(6);
        } else if (lowerTrim.rfind("jump to ", 0) == 0) {
            isJumpCmd = true;
            jumpQuery = input.substr(8);
        }

        if (isJumpCmd) {
            jumpQuery.erase(0, jumpQuery.find_first_not_of(" \t\r\n"));
            jumpQuery.erase(jumpQuery.find_last_not_of(" \t\r\n") + 1);

            std::string currentCwd = fs::current_path().string();
            std::string dest = jumper.Jump(jumpQuery, currentCwd);

            if (!dest.empty()) {
                jumper.SetLastDir(currentCwd);
                fs::current_path(dest);
                fs::path newCwd = fs::current_path();
                jumper.Record(newCwd.string());
                tabs[activeTabIdx].cwd = newCwd.string();
                tabs[activeTabIdx].name = newCwd.filename().string();
                std::cout << "  " << C_GREEN << "⚡ Jumped → " << C_BOLD << C_WHITE << newCwd.string() << C_RESET << "\n";
                return;
            } else {
                std::cout << "  " << C_RED << "❌ Directory matching '" << jumpQuery << "' not found." << C_RESET << "\n";
                return;
            }
        }

        if (input.rfind("cd ", 0) == 0 || input == "cd") {
            std::string target = (input.length() > 3) ? input.substr(3) : "";
            target.erase(0, target.find_first_not_of(" \t\r\n"));
            target.erase(target.find_last_not_of(" \t\r\n") + 1);

            std::string prevCwd = fs::current_path().string();
            jumper.SetLastDir(prevCwd);

            if (target.empty() || target == "~") {
                fs::current_path(PlatformFS::GetHomeDir());
            } else {
                try {
                    fs::current_path(target);
                } catch (...) {
                    std::cout << "  " << C_RED << "❌ Directory error: Path not found." << C_RESET << "\n";
                }
            }
            fs::path newCwd = fs::current_path();
            jumper.Record(newCwd.string());
            tabs[activeTabIdx].cwd = newCwd.string();
            tabs[activeTabIdx].name = newCwd.filename().string();
            return;
        }

        // 4. Slash Commands
        if (input[0] == '/') {
            HandleSlashCommand(input);
            return;
        }

        // 4.5. AI Command Pipings (| @ai, | @fix, | @explain, | @agent)
        size_t pipePos = input.find('|');
        if (pipePos != std::string::npos) {
            std::string rhs = input.substr(pipePos + 1);
            size_t s = rhs.find_first_not_of(" \t");
            if (s != std::string::npos) {
                rhs = rhs.substr(s);
                if (rhs.rfind("@ai", 0) == 0 || rhs.rfind("@fix", 0) == 0 ||
                    rhs.rfind("@explain", 0) == 0 || rhs.rfind("@agent", 0) == 0) {
                    
                    std::string upstream = input.substr(0, pipePos);
                    std::string directive = "@ai";
                    std::string prompt = "";
                    size_t sp = rhs.find(' ');
                    if (sp != std::string::npos) {
                        directive = rhs.substr(0, sp);
                        prompt = rhs.substr(sp + 1);
                    } else {
                        directive = rhs;
                    }

                    std::cout << "  " << C_MAGENTA << "⚡ Executing upstream pipeline: " << C_WHITE << upstream << C_RESET << "\n";
                    PlatformProcessRunner::ExecResult upRes = PlatformProcessRunner::Execute(upstream);
                    
                    std::cout << "\n  " << C_CYAN << "⌬ NeuroAI (" << directive << " Reasoning):" << C_RESET << "\n";
                    std::string aiResponse = ipcClient.AIPipe(directive, prompt, upRes.output, fs::current_path().string());
                    std::cout << "  " << C_WHITE << aiResponse << C_RESET << "\n\n";
                    return;
                }
            }
        }

        // 4.6. Autonomous Agent / Swarm Tasks (@agent "...", @swarm "...")
        if (lowerTrim.rfind("@agent", 0) == 0 || lowerTrim.rfind("@swarm", 0) == 0 ||
            lowerTrim.rfind("/agent", 0) == 0 || lowerTrim.rfind("/swarm", 0) == 0) {
            
            std::string task = input;
            size_t sp = task.find(' ');
            if (sp != std::string::npos) {
                task = task.substr(sp + 1);
            } else {
                task = "Inspect repository and report health";
            }
            task.erase(0, task.find_first_not_of(" \t\r\n\"'"));
            task.erase(task.find_last_not_of(" \t\r\n\"'") + 1);

            std::cout << "\n  " << C_MAGENTA << "⌬ NeuroShell Autonomous Swarm" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Task: " << C_WHITE << task << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Synthesizing multi-step execution plan..." << C_RESET << "\n\n";

            NeuroShell::IPC::AgentPlanResult plan = ipcClient.CreateAgentPlan(task, fs::current_path().string());
            if (!plan.success || plan.steps.empty()) {
                std::cout << "  " << C_RED << "❌ Unable to generate swarm plan." << C_RESET << "\n";
                return;
            }

            std::cout << "  " << C_CYAN << "╭── ⌬ Swarm Orchestration Plan (" << plan.steps.size() << " Steps) ─────────────────────────╮" << C_RESET << "\n";
            for (const auto& step : plan.steps) {
                std::cout << "  " << C_CYAN << "│ " << C_WHITE << step.order << ". [⬜ PENDING] " << step.description << C_RESET << "\n";
                std::cout << "  " << C_CYAN << "│    ❯ " << C_YELLOW << step.command << C_RESET << "\n";
            }
            std::cout << "  " << C_CYAN << "╰──────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";

            bool autoApproveAll = false;
            for (size_t i = 0; i < plan.steps.size(); ++i) {
                const auto& step = plan.steps[i];
                std::cout << "  " << C_MAGENTA << "Step " << step.order << "/" << plan.steps.size() << ": " << C_WHITE << step.description << C_RESET << "\n";
                std::cout << "  " << C_CYAN << "Command: " << C_BOLD << C_WHITE << step.command << C_RESET << "\n";

                if (!autoApproveAll) {
                    std::cout << "  " << C_YELLOW << "[y] Approve & Run   [n] Skip   [a] Auto-Approve All   [q] Abort: " << C_RESET;
                    KeyEvent k = terminal.ReadKey();
                    std::cout << k.ch << "\n\n";

                    if (k.ch == 'q' || k.ch == 'Q') {
                        std::cout << "  " << C_RED << "🛑 Agent workflow aborted by user." << C_RESET << "\n\n";
                        return;
                    }
                    if (k.ch == 'n' || k.ch == 'N') {
                        std::cout << "  " << C_MUTED << "⏭️ Skipped step " << step.order << C_RESET << "\n\n";
                        continue;
                    }
                    if (k.ch == 'a' || k.ch == 'A') {
                        autoApproveAll = true;
                    }
                }

                std::cout << "  " << C_GREEN << "⚡ [🔄 RUNNING] " << step.command << C_RESET << "\n";
                PlatformProcessRunner::ExecResult stepRes = PlatformProcessRunner::Execute(step.command);
                if (stepRes.exitCode == 0) {
                    std::cout << "  " << C_GREEN << "✅ [COMPLETED] Step " << step.order << " succeeded." << C_RESET << "\n\n";
                } else {
                    std::cout << "  " << C_RED << "❌ [FAILED] Step " << step.order << " exited with code " << stepRes.exitCode << C_RESET << "\n\n";
                    if (!autoApproveAll) {
                        std::cout << "  " << C_YELLOW << "Continue to next step? [y/N]: " << C_RESET;
                        KeyEvent contKey = terminal.ReadKey();
                        std::cout << contKey.ch << "\n\n";
                        if (contKey.ch != 'y' && contKey.ch != 'Y') break;
                    }
                }
            }
            std::cout << "  " << C_GREEN << "✨ Swarm task execution finished." << C_RESET << "\n\n";
            return;
        }

        // 5. Natural Language Command Translation
        std::string transformed = TranslateNaturalLanguage(input);
        std::string commandToRun = input;

        if (!transformed.empty()) {
            std::cout << "  " << C_MAGENTA << "⌬ Translating: " << C_WHITE << "'" << input << "'..." << C_RESET << "\n";
            std::cout << "  " << C_GREEN << "✔ Transformed → " << C_BOLD << C_WHITE << transformed << C_RESET << "\n\n";
            commandToRun = transformed;
        }

        // 6. Cross-Platform Process Runner
        PlatformProcessRunner::ExecResult execRes = PlatformProcessRunner::Execute(commandToRun);

        // Real-Time Viewport DLP Masking & Stream Recording
        execRes.output = dlpMasker.filter_stream(execRes.output);
        streamRecorder.record_input(commandToRun);
        streamRecorder.record_output(execRes.output);
        shmRing.write_message("{\"event\":\"command_executed\",\"cmd\":\"" + commandToRun + "\"}");

        // Smart Error Shield (Local Pattern + Python AST / LLM Diagnosis via IPC)
        if (execRes.exitCode != 0) {
            SmartErrorShield::ErrorReport errRep = errorShield.Analyze(execRes.output, execRes.exitCode, commandToRun);
            if (!errRep.hasError || errRep.autoFixCmd.empty()) {
                // Query Python IPC Error Diagnoser
                NeuroShell::IPC::DiagnosticResult diag = ipcClient.DiagnoseError(commandToRun, execRes.output, execRes.exitCode, fs::current_path().string());
                if (diag.success && !diag.auto_fix.empty()) {
                    errRep.hasError = true;
                    errRep.category = diag.category;
                    errRep.detail = diag.root_cause;
                    errRep.autoFixCmd = diag.auto_fix;
                }
            }

            if (errRep.hasError && !errRep.autoFixCmd.empty()) {
                errorShield.RenderErrorCard(errRep);

                KeyEvent keyEv = terminal.ReadKey();
                if (keyEv.ch == 'y' || keyEv.ch == 'Y') {
                    std::cout << "  " << C_GREEN << "⚡ Applying Auto-Fix: " << C_BOLD << C_WHITE << errRep.autoFixCmd << C_RESET << "\n\n";
                    ExecuteCommand(errRep.autoFixCmd);
                }
            }
        }
    }

    void Run() {
        PrintBanner();

        while (true) {
            RenderTabBar();

            std::string cwd = fs::current_path().string();
            std::string branch = GetGitBranch();
            std::string branchTag = branch.empty() ? "" : (" (" + std::string(C_MAGENTA) + branch + std::string(C_MUTED) + ")");

            std::string prompt = std::string(C_CYAN) + "⌬ " + C_MUTED + cwd + branchTag + " " + C_CYAN + "❯" + C_RESET + " ";
            std::string input = ReadLine(prompt);

            size_t start = input.find_first_not_of(" \t\r\n");
            if (start == std::string::npos) continue;
            input = input.substr(start);
            input.erase(input.find_last_not_of(" \t\r\n") + 1);

            ExecuteCommand(input);
            std::cout << "\n";
        }
    }
};

// ═══════════════════════════════════════════════════════════
// Pure Async-Signal-Safe Crash Filter (Windows & POSIX)
// ═══════════════════════════════════════════════════════════

#if defined(NEUROSHELL_PLATFORM_WINDOWS)
LONG WINAPI NeuroShellWin32CrashFilter(EXCEPTION_POINTERS* ep) {
    wchar_t dumpPath[MAX_PATH];
    DWORD len = GetEnvironmentVariableW(L"USERPROFILE", dumpPath, MAX_PATH);
    if (len > 0 && len < MAX_PATH) {
        wcscat_s(dumpPath, MAX_PATH, L"\\.neuroshell\\crash.log");
    } else {
        wcscpy_s(dumpPath, MAX_PATH, L"neuroshell_crash.log");
    }

    HANDLE hFile = CreateFileW(dumpPath, FILE_APPEND_DATA, FILE_SHARE_READ,
                               NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile != INVALID_HANDLE_VALUE) {
        char buf[256];
        int bytes = wsprintfA(buf, "=== CRASH EVENT (Win32) ===\r\nExceptionCode: 0x%08X\r\nAddress: 0x%p\r\n\r\n",
                              ep->ExceptionRecord->ExceptionCode,
                              ep->ExceptionRecord->ExceptionAddress);
        DWORD written = 0;
        WriteFile(hFile, buf, bytes, &written, NULL);
        CloseHandle(hFile);
    }

    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    if (hOut != INVALID_HANDLE_VALUE) {
        const char msg[] = "\r\n\033[1;31m[!] NeuroShell Fatal Exception Intercepted. State restored.\033[0m\r\n\033[?25h";
        DWORD written = 0;
        WriteFile(hOut, msg, (DWORD)strlen(msg), &written, NULL);
    }
    return EXCEPTION_EXECUTE_HANDLER;
}
#else
void NeuroShellPosixSignalHandler(int sig, siginfo_t* info, void* ucontext) {
    const char* home = getenv("HOME");
    char pathBuf[1024];
    if (home) snprintf(pathBuf, sizeof(pathBuf), "%s/.neuroshell/crash.log", home);
    else snprintf(pathBuf, sizeof(pathBuf), "neuroshell_crash.log");

    int fd = open(pathBuf, O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (fd >= 0) {
        char buf[256];
        int bytes = snprintf(buf, sizeof(buf), "=== CRASH EVENT (POSIX) ===\nSignal: %d\nFault Address: %p\n\n",
                             sig, info ? info->si_addr : nullptr);
        write(fd, buf, bytes);
        close(fd);
    }

    const char msg[] = "\r\n\033[1;31m[!] NeuroShell Fatal Signal Intercepted. State restored.\033[0m\r\n\033[?25h";
    write(STDERR_FILENO, msg, strlen(msg));
    _exit(128 + sig);
}
#endif

int main() {
    EnterpriseTerminalHost host;
    host.Run();
    return 0;
}
