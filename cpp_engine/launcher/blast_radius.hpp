// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// BlastRadiusAnalyzer — pre-execution impact preview for destructive
// commands (Phase 4 of the engineering roadmap).
//
// Before a command runs, the host answers: "what would this actually
// touch?" — by parsing the command line (quote-aware tokenizer, pipeline
// splitting), classifying destructive operations, resolving their target
// paths against the REAL filesystem (glob expansion + recursive inode/byte
// counting), and grading severity:
//
//   CRITICAL  system-destroying: rm -rf /, ~, /etc…; dd/mkfs onto a block
//             device; chmod -R 777 /
//   HIGH      large irreversible loss: recursive delete resolving to
//             >1000 files or >1 GiB; git reset --hard / clean -f;
//             find -delete
//   MEDIUM    bounded irreversible loss: rm of existing files, mv/cp over
//             an existing file, > truncation of a non-empty file,
//             shred/truncate
//   LOW/NONE  everything else — never prompted, zero friction
//
// Scan cost is HARD-CAPPED (default 50 000 inodes / 500 ms wall-clock,
// injectable for tests): the preview must never feel slower than the
// command. When a cap is hit the report says "at least N files" and the
// severity grade assumes the worst.
//
// This is a HEURISTIC SAFETY NET, not a sandbox: a sufficiently obfuscated
// command (base64 | sh …) can evade static classification. The design goal
// is catching the fat-fingered 2 a.m. `rm -rf` with a wrong variable —
// kernel-level enforcement is Phase 8.
#pragma once

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <regex>
#include <string>
#include <vector>

namespace neuroshell {

enum class BlastSeverity : int { None = 0, Low = 1, Medium = 2, High = 3, Critical = 4 };

inline const char* BlastSeverityName(BlastSeverity s) {
    switch (s) {
        case BlastSeverity::None: return "NONE";
        case BlastSeverity::Low: return "LOW";
        case BlastSeverity::Medium: return "MEDIUM";
        case BlastSeverity::High: return "HIGH";
        case BlastSeverity::Critical: return "CRITICAL";
    }
    return "?";
}

struct BlastTarget {
    std::string path;        // as resolved (absolute where possible)
    uint64_t files = 0;      // regular files under the target (1 for a file)
    uint64_t dirs = 0;
    uint64_t bytes = 0;
    bool exists = false;
    bool is_dir = false;
    bool scan_capped = false; // counters are lower bounds
};

struct BlastOperation {
    std::string verb;        // "delete", "overwrite", "truncate", "device-write",
                             // "vcs-destructive", "permission-change"
    std::string segment;     // the pipeline segment that triggered this
    std::vector<BlastTarget> targets;
    BlastSeverity severity = BlastSeverity::None;
    std::string note;        // human context ("untracked files", "block device", …)
};

struct BlastReport {
    BlastSeverity severity = BlastSeverity::None;
    std::vector<BlastOperation> operations;
    uint64_t total_files = 0;
    uint64_t total_bytes = 0;
    bool scan_capped = false;

    bool NeedsConfirmation() const { return severity >= BlastSeverity::Medium; }
};

class BlastRadiusAnalyzer {
public:
    // Scan caps (injectable for tests).
    uint64_t max_inodes = 50000;
    std::chrono::milliseconds deadline{500};

    // ── shell-syntax helpers (public: unit-tested directly) ──

    // Split a command line into pipeline/sequence segments on | ; && ||
    // (quote- and escape-aware; redirection stays inside its segment).
    static std::vector<std::string> SplitSegments(const std::string& cmd) {
        std::vector<std::string> out;
        std::string cur;
        char quote = 0;
        for (size_t i = 0; i < cmd.size(); ++i) {
            char c = cmd[i];
            if (quote) {
                cur += c;
                if (c == quote && (quote != '"' || i == 0 || cmd[i - 1] != '\\')) quote = 0;
                continue;
            }
            if (c == '\'' || c == '"') {
                quote = c;
                cur += c;
                continue;
            }
            if (c == '\\' && i + 1 < cmd.size()) {
                cur += c;
                cur += cmd[++i];
                continue;
            }
            bool split = false;
            if (c == ';') split = true;
            else if (c == '|') {
                split = true;
                if (i + 1 < cmd.size() && cmd[i + 1] == '|') ++i;
            } else if (c == '&' && i + 1 < cmd.size() && cmd[i + 1] == '&') {
                split = true;
                ++i;
            }
            if (split) {
                if (!Trim(cur).empty()) out.push_back(Trim(cur));
                cur.clear();
            } else {
                cur += c;
            }
        }
        if (!Trim(cur).empty()) out.push_back(Trim(cur));
        return out;
    }

    // POSIX-ish tokenizer: handles '…', "…", backslash escapes. Redirection
    // operators become their own tokens (">", ">>") so truncation targets
    // are visible.
    static std::vector<std::string> Tokenize(const std::string& seg) {
        std::vector<std::string> toks;
        std::string cur;
        bool has_cur = false;
        char quote = 0;
        for (size_t i = 0; i < seg.size(); ++i) {
            char c = seg[i];
            if (quote) {
                if (c == quote) quote = 0;
                else cur += c;
                has_cur = true;
                continue;
            }
            switch (c) {
                case '\'':
                case '"':
                    quote = c;
                    has_cur = true;
                    break;
                case '\\':
                    if (i + 1 < seg.size()) cur += seg[++i];
                    has_cur = true;
                    break;
                case ' ':
                case '\t':
                    if (has_cur) {
                        toks.push_back(cur);
                        cur.clear();
                        has_cur = false;
                    }
                    break;
                case '>': {
                    if (has_cur && !cur.empty()) {
                        // strip fd prefix like 2> — the fd digit belongs to
                        // the operator, not a target word
                        if (cur.size() == 1 && cur[0] >= '0' && cur[0] <= '9') {
                            cur.clear();
                        } else {
                            toks.push_back(cur);
                            cur.clear();
                        }
                    }
                    if (i + 1 < seg.size() && seg[i + 1] == '>') {
                        toks.push_back(">>");
                        ++i;
                    } else {
                        toks.push_back(">");
                    }
                    has_cur = false;
                    break;
                }
                default:
                    cur += c;
                    has_cur = true;
            }
        }
        if (has_cur) toks.push_back(cur);
        return toks;
    }

    // ── the analyzer ─────────────────────────────────────────

    BlastReport Analyze(const std::string& command, const std::string& cwd) const {
        BlastReport report;
        for (const std::string& seg : SplitSegments(command)) {
            std::vector<std::string> argv = Tokenize(seg);
            if (argv.empty()) continue;

            // unwrap benign prefixes
            size_t start = 0;
            while (start < argv.size() &&
                   (argv[start] == "sudo" || argv[start] == "doas" || argv[start] == "env" ||
                    argv[start] == "nohup" || argv[start] == "time" ||
                    argv[start].find('=') != std::string::npos))
                ++start;
            if (start >= argv.size()) continue;

            std::vector<std::string> a(argv.begin() + static_cast<long>(start), argv.end());
            ClassifySegment(seg, a, cwd, report);
        }

        for (const auto& op : report.operations) {
            if (op.severity > report.severity) report.severity = op.severity;
            for (const auto& t : op.targets) {
                report.total_files += t.files;
                report.total_bytes += t.bytes;
                if (t.scan_capped) report.scan_capped = true;
            }
        }
        return report;
    }

    // ── filesystem resolution (public: unit-tested directly) ──

    // Resolve one command-line path argument: absolute-ize against cwd,
    // expand a trailing-component glob, and measure each hit.
    std::vector<BlastTarget> ResolveTargets(const std::string& raw, const std::string& cwd) const {
        namespace fs = std::filesystem;
        std::vector<BlastTarget> out;
        std::string expanded = ExpandTilde(raw);
        fs::path p(expanded);
        if (p.is_relative()) p = fs::path(cwd) / p;

        const std::string comp = p.filename().string();
        if (HasGlob(comp)) {
            std::error_code ec;
            std::regex rx = GlobToRegex(comp);
            fs::path parent = p.parent_path();
            if (fs::exists(parent, ec)) {
                for (fs::directory_iterator it(parent, fs::directory_options::skip_permission_denied, ec), end;
                     !ec && it != end; it.increment(ec)) {
                    std::string name = it->path().filename().string();
                    if (name != "." && name != ".." && std::regex_match(name, rx)) {
                        out.push_back(Measure(it->path()));
                    }
                }
            }
            if (out.empty()) {
                BlastTarget t;
                t.path = p.string();
                out.push_back(t); // glob matched nothing — reported as missing
            }
            return out;
        }

        out.push_back(Measure(p));
        return out;
    }

    // Bounded recursive measurement of one path.
    BlastTarget Measure(const std::filesystem::path& p) const {
        namespace fs = std::filesystem;
        BlastTarget t;
        std::error_code ec;
        fs::path canon = fs::weakly_canonical(p, ec);
        t.path = ec ? p.string() : canon.string();

        fs::file_status st = fs::symlink_status(p, ec);
        if (ec || st.type() == fs::file_type::not_found) return t;
        t.exists = true;

        if (fs::is_symlink(st)) { // count the link itself, never follow
            t.files = 1;
            return t;
        }
        if (fs::is_regular_file(st)) {
            t.files = 1;
            t.bytes = static_cast<uint64_t>(fs::file_size(p, ec));
            return t;
        }
        if (!fs::is_directory(st)) { // device/fifo/socket
            t.files = 1;
            return t;
        }

        t.is_dir = true;
        t.dirs = 1;
        const auto start = std::chrono::steady_clock::now();
        uint64_t inodes = 0;
        fs::recursive_directory_iterator it(p, fs::directory_options::skip_permission_denied, ec), end;
        for (; !ec && it != end; it.increment(ec)) {
            ++inodes;
            std::error_code sec;
            if (it->is_directory(sec)) {
                ++t.dirs;
            } else {
                ++t.files;
                if (it->is_regular_file(sec)) {
                    t.bytes += static_cast<uint64_t>(it->file_size(sec));
                }
            }
            if (inodes >= max_inodes ||
                (inodes % 256 == 0 &&
                 std::chrono::steady_clock::now() - start > deadline)) {
                t.scan_capped = true;
                break;
            }
        }
        return t;
    }

    // ── severity policy (public: unit-tested directly) ──

    static bool IsSystemCriticalPath(const std::string& path) {
        static const char* kCritical[] = {
            "/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
            "/var", "/boot", "/opt", "/home", "/root", "/dev", "/proc", "/sys",
            "c:", "c:/", "c:\\", "c:/windows", "c:\\windows",
            "c:/program files", "c:\\program files", "c:/users", "c:\\users",
        };
        std::string norm = path;
        for (char& c : norm) {
            if (c == '\\') c = '/';
            else c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
        }
        while (norm.size() > 1 && norm.back() == '/') norm.pop_back();
        if (norm == "/" || norm == "c:" || (norm.size() == 2 && norm[1] == ':')) return true;
        for (const char* c : kCritical) {
            std::string crit = c;
            for (char& ch : crit) {
                if (ch == '\\') ch = '/';
                else ch = static_cast<char>(tolower(static_cast<unsigned char>(ch)));
            }
            while (crit.size() > 1 && crit.back() == '/') crit.pop_back();
            if (norm == crit || norm == "/" + crit || (norm.size() >= 2 && norm.substr(2) == crit))
                return true;
        }
        if (const char* home = std::getenv("HOME")) {
            std::string h = home;
            for (char& ch : h) {
                if (ch == '\\') ch = '/';
                else ch = static_cast<char>(tolower(static_cast<unsigned char>(ch)));
            }
            while (h.size() > 1 && h.back() == '/') h.pop_back();
            if (!h.empty() && (norm == h || norm == "/" + h)) return true;
        }
        if (const char* userprofile = std::getenv("USERPROFILE")) {
            std::string u = userprofile;
            for (char& ch : u) {
                if (ch == '\\') ch = '/';
                else ch = static_cast<char>(tolower(static_cast<unsigned char>(ch)));
            }
            while (u.size() > 1 && u.back() == '/') u.pop_back();
            if (!u.empty() && (norm == u || norm == "/" + u)) return true;
        }
        return false;
    }

    static bool IsBlockDevicePath(const std::string& path) {
        return path.rfind("/dev/", 0) == 0 && path != "/dev/null" && path != "/dev/zero" &&
               path != "/dev/stdout" && path != "/dev/stderr" && path != "/dev/tty" &&
               path != "/dev/urandom" && path != "/dev/random";
    }

private:
    static std::string Trim(const std::string& s) {
        size_t b = s.find_first_not_of(" \t");
        if (b == std::string::npos) return "";
        size_t e = s.find_last_not_of(" \t");
        return s.substr(b, e - b + 1);
    }

    static std::string ExpandTilde(const std::string& s) {
        if (s == "~" || s.rfind("~/", 0) == 0) {
            if (const char* home = std::getenv("HOME"))
                return std::string(home) + s.substr(1);
        }
        return s;
    }

    static bool HasGlob(const std::string& s) {
        return s.find_first_of("*?[") != std::string::npos;
    }

    static std::regex GlobToRegex(const std::string& glob) {
        std::string rx;
        for (char c : glob) {
            switch (c) {
                case '*': rx += "[^/]*"; break;
                case '?': rx += '.'; break;
                case '.': rx += "\\."; break;
                case '\\': case '+': case '(': case ')': case '^': case '$':
                case '{': case '}': case ']':
                    rx += '\\'; rx += c; break;
                case '[': rx += '['; break;
                default: rx += c;
            }
        }
        return std::regex(rx);
    }

    static bool IsFlag(const std::string& s) { return !s.empty() && s[0] == '-'; }

    static bool HasRecursiveFlag(const std::vector<std::string>& a) {
        for (const auto& s : a) {
            if (s == "--recursive" || s == "-R") return true;
            if (s.size() >= 2 && s[0] == '-' && s[1] != '-' &&
                (s.find('r') != std::string::npos || s.find('R') != std::string::npos))
                return true;
        }
        return false;
    }

    void ClassifySegment(const std::string& seg, const std::vector<std::string>& a,
                         const std::string& cwd, BlastReport& report) const {
        const std::string& cmd = a[0];

        auto nonFlagArgs = [&](size_t from) {
            std::vector<std::string> out;
            for (size_t i = from; i < a.size(); ++i) {
                if (a[i] == ">" || a[i] == ">>") { ++i; continue; } // skip redirect + target
                if (!IsFlag(a[i]) && a[i] != "--") out.push_back(a[i]);
            }
            return out;
        };

        // ── rm / rmdir / shred / unlink ──
        if (cmd == "rm" || cmd == "rmdir" || cmd == "shred" || cmd == "unlink") {
            BlastOperation op;
            op.verb = "delete";
            op.segment = seg;
            bool recursive = (cmd == "rm") && HasRecursiveFlag(a);
            for (const std::string& raw : nonFlagArgs(1)) {
                if (IsSystemCriticalPath(raw)) {
                    op.severity = BlastSeverity::Critical;
                    op.note = "system-critical path";
                }
                for (BlastTarget& t : ResolveTargets(raw, cwd)) {
                    if (IsSystemCriticalPath(t.path) || IsSystemCriticalPath(raw)) {
                        op.severity = BlastSeverity::Critical;
                        op.note = "system-critical path";
                    }
                    op.targets.push_back(std::move(t));
                }
            }
            FinishDeleteSeverity(op, recursive);
            if (!op.targets.empty()) report.operations.push_back(std::move(op));
            return;
        }

        // ── mv / cp onto an existing file ──
        if ((cmd == "mv" || cmd == "cp") && a.size() >= 3) {
            std::vector<std::string> args = nonFlagArgs(1);
            if (args.size() >= 2) {
                BlastTarget dest = Measure(AbsPath(ExpandTilde(args.back()), cwd));
                if (dest.exists && !dest.is_dir) {
                    BlastOperation op;
                    op.verb = "overwrite";
                    op.segment = seg;
                    op.note = "destination file exists and will be replaced";
                    op.severity = BlastSeverity::Medium;
                    op.targets.push_back(std::move(dest));
                    report.operations.push_back(std::move(op));
                }
            }
            return;
        }

        // ── dd / mkfs / fdisk / parted onto devices ──
        if (cmd == "dd") {
            for (const auto& s : a) {
                if (s.rfind("of=", 0) == 0) {
                    std::string target = s.substr(3);
                    BlastOperation op;
                    op.verb = "device-write";
                    op.segment = seg;
                    if (IsBlockDevicePath(target)) {
                        op.severity = BlastSeverity::Critical;
                        op.note = "raw write to a device node";
                    } else {
                        op.verb = "overwrite";
                        op.severity = BlastSeverity::Medium;
                        op.note = "dd overwrites the output file";
                    }
                    op.targets.push_back(Measure(AbsPath(ExpandTilde(target), cwd)));
                    report.operations.push_back(std::move(op));
                }
            }
            return;
        }
        if (cmd.rfind("mkfs", 0) == 0 || cmd == "fdisk" || cmd == "parted" || cmd == "wipefs") {
            BlastOperation op;
            op.verb = "device-write";
            op.segment = seg;
            op.severity = BlastSeverity::Critical;
            op.note = "filesystem/partition tool";
            for (const std::string& raw : nonFlagArgs(1)) {
                op.targets.push_back(Measure(raw));
            }
            report.operations.push_back(std::move(op));
            return;
        }

        // ── truncate ──
        if (cmd == "truncate") {
            BlastOperation op;
            op.verb = "truncate";
            op.segment = seg;
            op.severity = BlastSeverity::Medium;
            for (const std::string& raw : nonFlagArgs(1)) {
                // skip the numeric argument to -s
                if (!raw.empty() && (isdigit(static_cast<unsigned char>(raw[0])) || raw[0] == '+'))
                    continue;
                for (BlastTarget& t : ResolveTargets(raw, cwd)) op.targets.push_back(std::move(t));
            }
            if (!op.targets.empty()) report.operations.push_back(std::move(op));
            return;
        }

        // ── chmod / chown -R ──
        if ((cmd == "chmod" || cmd == "chown") && HasRecursiveFlag(a)) {
            BlastOperation op;
            op.verb = "permission-change";
            op.segment = seg;
            op.severity = BlastSeverity::Medium;
            std::vector<std::string> args = nonFlagArgs(1);
            for (size_t i = 1; i < args.size(); ++i) { // args[0] = mode/owner
                if (IsSystemCriticalPath(args[i])) {
                    op.severity = BlastSeverity::Critical;
                    op.note = "recursive permission change on system path";
                }
                for (BlastTarget& t : ResolveTargets(args[i], cwd)) {
                    if (IsSystemCriticalPath(t.path) || IsSystemCriticalPath(args[i])) {
                        op.severity = BlastSeverity::Critical;
                        op.note = "recursive permission change on system path";
                    }
                    op.targets.push_back(std::move(t));
                }
            }
            if (op.severity < BlastSeverity::High) {
                for (const auto& t : op.targets) {
                    if (t.files > 1000) op.severity = BlastSeverity::High;
                }
            }
            if (!op.targets.empty()) report.operations.push_back(std::move(op));
            return;
        }

        // ── git destructive verbs ──
        if (cmd == "git" && a.size() >= 2) {
            const std::string& sub = a[1];
            bool destructive = false;
            std::string note;
            if (sub == "clean") {
                for (const auto& s : a) {
                    if (IsFlag(s) && s.find('f') != std::string::npos) destructive = true;
                }
                note = "permanently deletes untracked files";
            } else if (sub == "reset") {
                for (const auto& s : a) {
                    if (s == "--hard") destructive = true;
                }
                note = "discards uncommitted changes";
            } else if (sub == "checkout" || sub == "restore") {
                for (size_t i = 2; i < a.size(); ++i) {
                    if (a[i] == "--" || a[i] == "." || a[i] == "--force" || a[i] == "-f")
                        destructive = true;
                }
                note = "overwrites working-tree changes";
            } else if (sub == "push") {
                for (const auto& s : a) {
                    if (s == "--force" || s == "-f") destructive = true;
                }
                note = "force-push rewrites remote history";
            } else if (sub == "branch") {
                for (const auto& s : a) {
                    if (s == "-D") destructive = true;
                }
                note = "force-deletes a branch (unmerged commits lost)";
            }
            if (destructive) {
                BlastOperation op;
                op.verb = "vcs-destructive";
                op.segment = seg;
                op.severity = BlastSeverity::High;
                op.note = note;
                report.operations.push_back(std::move(op));
            }
            return;
        }

        // ── find … -delete / -exec rm ──
        if (cmd == "find") {
            bool deletes = false;
            for (size_t i = 1; i < a.size(); ++i) {
                if (a[i] == "-delete") deletes = true;
                if (a[i] == "-exec" && i + 1 < a.size() && (a[i + 1] == "rm" || a[i + 1] == "shred"))
                    deletes = true;
            }
            if (deletes) {
                BlastOperation op;
                op.verb = "delete";
                op.segment = seg;
                op.note = "find with -delete/-exec rm";
                std::string root = (a.size() >= 2 && !IsFlag(a[1])) ? a[1] : ".";
                for (BlastTarget& t : ResolveTargets(root, cwd)) {
                    if (IsSystemCriticalPath(t.path)) op.severity = BlastSeverity::Critical;
                    op.targets.push_back(std::move(t));
                }
                FinishDeleteSeverity(op, /*recursive=*/true);
                report.operations.push_back(std::move(op));
            }
            return;
        }

        // ── > truncation of an existing non-empty file ──
        for (size_t i = 0; i + 1 < a.size(); ++i) {
            if (a[i] == ">") {
                BlastTarget t = Measure(AbsPath(ExpandTilde(a[i + 1]), cwd));
                if (t.exists && !t.is_dir && t.bytes > 0) {
                    BlastOperation op;
                    op.verb = "truncate";
                    op.segment = seg;
                    op.severity = BlastSeverity::Medium;
                    op.note = "existing file content will be discarded";
                    op.targets.push_back(std::move(t));
                    report.operations.push_back(std::move(op));
                }
            }
        }
    }

    void FinishDeleteSeverity(BlastOperation& op, bool recursive) const {
        if (op.severity == BlastSeverity::Critical) return;
        uint64_t files = 0, bytes = 0;
        bool any_exists = false, capped = false;
        for (const auto& t : op.targets) {
            files += t.files;
            bytes += t.bytes;
            any_exists = any_exists || t.exists;
            capped = capped || t.scan_capped;
        }
        if (!any_exists) {
            op.severity = BlastSeverity::None; // nothing to destroy
            op.note = "no matching files exist";
            return;
        }
        if (capped || files > 1000 || bytes > (1ull << 30)) {
            op.severity = BlastSeverity::High;
        } else if (recursive || files > 0) {
            op.severity = BlastSeverity::Medium;
        }
    }

    static std::filesystem::path AbsPath(const std::string& raw, const std::string& cwd) {
        std::filesystem::path p(raw);
        return p.is_relative() ? std::filesystem::path(cwd) / p : p;
    }
};

} // namespace neuroshell
