// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// ═══════════════════════════════════════════════════════════════════
// Phase 5 (v5.13): Universal Undo — CoW snapshots of write-targets
// ═══════════════════════════════════════════════════════════════════
//
// Before a confirmed destructive command executes, the launcher snapshots
// every existing write-target (as resolved by the Phase 4 BlastRadiusAnalyzer)
// into ~/.neuroshell/undo/<txn>/. `undo` restores the most recent transaction.
//
// Key properties:
//   • Copy-on-write first: on Linux, FICLONE reflinks share extents with the
//     original, so snapshotting a 10 GiB tree on btrfs/XFS is near-free.
//     On APFS (macOS), clonefile(2) does the same. When the filesystem cannot
//     reflink (ext4, tmpfs), we fall back to a real copy — bounded by
//     max_copy_bytes (default 512 MiB) so a snapshot can never eat the disk.
//   • Bounded: max_snapshot_inodes caps the walk; if a snapshot would exceed
//     any budget it is skipped cleanly (partial txn dir removed) and the
//     command still runs — undo is best-effort, never a blocker.
//   • Durable manifest: line-oriented, tab-escaped format (no JSON parser
//     needed to restore), written to manifest.tmp then renamed, and only a
//     manifest ending in the `complete` sentinel is ever restored.
//   • GC by age + count + size budget runs on every Begin().
//   • Works outside git repos — this is filesystem-level, not VCS-level.
//
// Explicit non-goals: block-device writes (dd of=/dev/sdX) and VCS-destructive
// verbs (git reset --hard has the reflog) are not snapshotted; permission-only
// changes (chmod -R) are metadata we do not journal in v1.

#pragma once

#include <string>
#include <vector>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <filesystem>
#include <system_error>
#include <chrono>

#if defined(__linux__)
  #include <fcntl.h>
  #include <unistd.h>
  #include <sys/ioctl.h>
  #include <sys/stat.h>
  #ifndef FICLONE
    #define FICLONE 0x40049409
  #endif
#elif defined(__APPLE__)
  #include <sys/attr.h>
  #include <sys/clonefile.h>
#endif

#include "blast_radius.hpp"

namespace neuroshell {

namespace ufs = std::filesystem;

// ───────────────────────────────────────────────────────────────────
// Manifest escaping: \ → \\, TAB → \t, LF → \n  (paths & commands)
// ───────────────────────────────────────────────────────────────────
inline std::string UndoEscape(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        if (c == '\\') out += "\\\\";
        else if (c == '\t') out += "\\t";
        else if (c == '\n') out += "\\n";
        else out += c;
    }
    return out;
}

inline std::string UndoUnescape(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '\\' && i + 1 < s.size()) {
            char n = s[++i];
            if (n == 't') out += '\t';
            else if (n == 'n') out += '\n';
            else out += n;
        } else {
            out += s[i];
        }
    }
    return out;
}

struct UndoEntry {
    char type = 'f';           // 'f' file, 'd' directory, 'l' symlink
    std::string original;      // absolute original path
    std::string snapshot_rel;  // path under <txn>/data/
};

struct UndoTransaction {
    std::string id;
    double ts = 0.0;
    std::string command;
    std::string cwd;
    uint64_t bytes = 0;
    uint64_t files = 0;
    bool complete = false;
    std::vector<UndoEntry> entries;
    ufs::path dir;             // txn directory on disk
};

enum class SnapshotStatus { Saved, SkippedTooLarge, SkippedNothingToSave, Failed, Disabled };

struct SnapshotResult {
    SnapshotStatus status = SnapshotStatus::SkippedNothingToSave;
    std::string txn_id;
    uint64_t files = 0;
    uint64_t bytes = 0;        // logical bytes protected (reflinked or copied)
    uint64_t copied_bytes = 0; // bytes physically copied (0 when fully reflinked)
    std::string reason;        // human context when not Saved
};

struct RestoreResult {
    bool ok = false;
    std::string txn_id;
    std::string command;       // the command this undo reverts
    uint64_t files_restored = 0;
    std::string error;
};

class UndoEngine {
public:
    // Budgets (public + injectable for tests)
    uint64_t max_copy_bytes = 512ull * 1024 * 1024;  // copy-fallback ceiling
    uint64_t max_snapshot_inodes = 50000;
    size_t   gc_max_transactions = 20;
    uint64_t gc_max_total_bytes = 2ull * 1024 * 1024 * 1024;
    int64_t  gc_max_age_seconds = 7 * 24 * 3600;
    bool     allow_reflink = true;                   // false forces the copy path (tests)

    explicit UndoEngine(ufs::path root) : root_(std::move(root)) {}

    const ufs::path& Root() const { return root_; }

    // ── Snapshot the write-targets of a confirmed destructive command ──
    SnapshotResult SnapshotBeforeExecute(const BlastReport& report,
                                         const std::string& command,
                                         const std::string& cwd) {
        SnapshotResult res;

        // Collect unique, existing, snapshot-able targets. Only content-
        // destroying verbs; device writes / VCS verbs / perm changes are out.
        std::vector<const BlastTarget*> targets;
        uint64_t logical_bytes = 0, logical_files = 0;
        for (const auto& op : report.operations) {
            if (op.verb != "delete" && op.verb != "overwrite" && op.verb != "truncate")
                continue;
            for (const auto& t : op.targets) {
                if (!t.exists) continue;
                bool dup = false;
                for (const auto* p : targets)
                    if (p->path == t.path) { dup = true; break; }
                if (dup) continue;
                targets.push_back(&t);
                logical_bytes += t.bytes;
                logical_files += t.files;
            }
        }
        if (targets.empty()) {
            res.status = SnapshotStatus::SkippedNothingToSave;
            res.reason = "no snapshot-able targets";
            return res;
        }
        if (logical_files > max_snapshot_inodes) {
            res.status = SnapshotStatus::SkippedTooLarge;
            res.reason = "too many files to snapshot (" + std::to_string(logical_files) + ")";
            return res;
        }

        GarbageCollect();

        // Transaction id: epoch-microseconds → lexicographically sortable.
        auto now = std::chrono::system_clock::now().time_since_epoch();
        uint64_t us = (uint64_t)std::chrono::duration_cast<std::chrono::microseconds>(now).count();
        std::string id = "txn-" + std::to_string(us);
        ufs::path txnDir = root_ / id;
        ufs::path dataDir = txnDir / "data";

        std::error_code ec;
        ufs::create_directories(dataDir, ec);
        if (ec) {
            res.status = SnapshotStatus::Failed;
            res.reason = "cannot create " + txnDir.string();
            return res;
        }

        uint64_t copied = 0;    // physically copied bytes (reflinks don't count)
        uint64_t inodes = 0;
        std::vector<UndoEntry> entries;
        bool over_budget = false;

        for (size_t i = 0; i < targets.size(); ++i) {
            const BlastTarget& t = *targets[i];
            ufs::path src = t.path;
            std::string rel = std::to_string(i) + "_" + src.filename().string();
            ufs::path dst = dataDir / rel;

            UndoEntry e;
            e.original = src.string();
            e.snapshot_rel = rel;

            std::error_code sec;
            auto st = ufs::symlink_status(src, sec);
            if (sec) { over_budget = true; break; }

            if (ufs::is_symlink(st)) {
                e.type = 'l';
                ufs::copy_symlink(src, dst, sec);
                if (sec) { over_budget = true; break; }
                ++inodes;
            } else if (ufs::is_directory(st)) {
                e.type = 'd';
                if (!SnapshotTree(src, dst, copied, inodes)) { over_budget = true; break; }
            } else if (ufs::is_regular_file(st)) {
                e.type = 'f';
                if (!SnapshotFile(src, dst, copied, inodes)) { over_budget = true; break; }
            } else {
                continue; // sockets/fifos: not snapshot-able, not fatal
            }
            entries.push_back(std::move(e));
        }

        if (over_budget || entries.empty()) {
            ufs::remove_all(txnDir, ec);
            res.status = over_budget ? SnapshotStatus::SkippedTooLarge
                                     : SnapshotStatus::SkippedNothingToSave;
            res.reason = over_budget
                ? ("copy budget exceeded (limit " + std::to_string(max_copy_bytes / (1024 * 1024)) + " MiB on non-CoW filesystem)")
                : "no snapshot-able targets";
            return res;
        }

        // Manifest: tmp-write + rename; `complete` sentinel is the commit mark.
        {
            std::ofstream m(txnDir / "manifest.tmp", std::ios::binary);
            if (!m) {
                ufs::remove_all(txnDir, ec);
                res.status = SnapshotStatus::Failed;
                res.reason = "cannot write manifest";
                return res;
            }
            m << "neuroshell-undo v1\n";
            m << "id\t" << id << "\n";
            m << "ts\t" << std::to_string((double)us / 1e6) << "\n";
            m << "command\t" << UndoEscape(command) << "\n";
            m << "cwd\t" << UndoEscape(cwd) << "\n";
            m << "bytes\t" << logical_bytes << "\n";
            m << "files\t" << logical_files << "\n";
            for (const auto& e : entries)
                m << "entry\t" << e.type << "\t" << UndoEscape(e.snapshot_rel)
                  << "\t" << UndoEscape(e.original) << "\n";
            m << "complete\n";
        }
        ufs::rename(txnDir / "manifest.tmp", txnDir / "manifest", ec);
        if (ec) {
            ufs::remove_all(txnDir, ec);
            res.status = SnapshotStatus::Failed;
            res.reason = "manifest rename failed";
            return res;
        }

        res.status = SnapshotStatus::Saved;
        res.txn_id = id;
        res.files = logical_files;
        res.bytes = logical_bytes;
        res.copied_bytes = copied;
        return res;
    }

    // ── Restore the most recent complete transaction ──
    RestoreResult Undo() {
        RestoreResult r;
        std::vector<UndoTransaction> txns = ListTransactions();
        if (txns.empty()) {
            r.error = "nothing to undo";
            return r;
        }
        const UndoTransaction& t = txns.front(); // newest first
        r.txn_id = t.id;
        r.command = t.command;

        for (const auto& e : t.entries) {
            ufs::path snap = t.dir / "data" / e.snapshot_rel;
            ufs::path orig = e.original;
            std::error_code ec;

            if (!ufs::exists(ufs::symlink_status(snap, ec))) {
                r.error = "snapshot data missing: " + snap.string();
                return r;
            }
            ufs::create_directories(orig.parent_path(), ec);

            if (e.type == 'l') {
                ufs::remove(orig, ec);
                ufs::copy_symlink(snap, orig, ec);
                if (ec) { r.error = "restore failed: " + orig.string(); return r; }
                r.files_restored += 1;
            } else if (e.type == 'd') {
                ufs::remove_all(orig, ec); // replace whatever partially remains
                ufs::create_directories(orig, ec);
                uint64_t n = 0;
                if (!RestoreTree(snap, orig, n)) {
                    r.error = "restore failed: " + orig.string();
                    return r;
                }
                r.files_restored += n;
            } else {
                ufs::remove(orig, ec);
                if (!RestoreFile(snap, orig)) {
                    r.error = "restore failed: " + orig.string();
                    return r;
                }
                r.files_restored += 1;
            }
        }

        // Consume the transaction only after a fully successful restore.
        std::error_code ec;
        ufs::remove_all(t.dir, ec);
        r.ok = true;
        return r;
    }

    // ── Newest-first list of complete transactions ──
    std::vector<UndoTransaction> ListTransactions() const {
        std::vector<UndoTransaction> out;
        std::error_code ec;
        if (!ufs::is_directory(root_, ec)) return out;
        for (const auto& d : ufs::directory_iterator(root_, ec)) {
            if (!d.is_directory()) continue;
            UndoTransaction t;
            if (ReadManifest(d.path(), t) && t.complete) out.push_back(std::move(t));
        }
        std::sort(out.begin(), out.end(),
                  [](const UndoTransaction& a, const UndoTransaction& b) { return a.id > b.id; });
        return out;
    }

    // ── GC: age, count, and size budgets (oldest evicted first) ──
    void GarbageCollect() {
        std::vector<UndoTransaction> txns = ListTransactions(); // newest first
        double now = (double)std::chrono::duration_cast<std::chrono::seconds>(
                         std::chrono::system_clock::now().time_since_epoch()).count();
        uint64_t total = 0;
        size_t kept = 0;
        std::error_code ec;
        for (const auto& t : txns) {
            total += t.bytes;
            ++kept;
            bool evict = kept > gc_max_transactions ||
                         total > gc_max_total_bytes ||
                         (now - t.ts) > (double)gc_max_age_seconds;
            if (evict) ufs::remove_all(t.dir, ec);
        }
        // Sweep incomplete/corrupt txn dirs (crashed mid-snapshot).
        for (const auto& d : ufs::directory_iterator(root_, ec)) {
            if (!d.is_directory()) continue;
            if (!ufs::exists(d.path() / "manifest")) ufs::remove_all(d.path(), ec);
        }
    }

    // ── Reflink-first single-file clone (public: reused by tests) ──
    // Returns false only when the file could not be preserved at all.
    bool SnapshotFile(const ufs::path& src, const ufs::path& dst,
                      uint64_t& copied_bytes, uint64_t& inodes) {
        if (++inodes > max_snapshot_inodes) return false;
        if (allow_reflink && ReflinkFile(src, dst)) return true;
        std::error_code ec;
        uint64_t sz = (uint64_t)ufs::file_size(src, ec);
        if (ec) sz = 0;
        if (copied_bytes + sz > max_copy_bytes) return false;
        ufs::copy_file(src, dst, ufs::copy_options::overwrite_existing, ec);
        if (ec) return false;
        copied_bytes += sz;
        return true;
    }

private:
    ufs::path root_;

    static bool ReflinkFile(const ufs::path& src, const ufs::path& dst) {
#if defined(__linux__)
        int in = ::open(src.c_str(), O_RDONLY | O_CLOEXEC);
        if (in < 0) return false;
        struct stat st{};
        if (::fstat(in, &st) != 0) { ::close(in); return false; }
        int out = ::open(dst.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, st.st_mode & 07777);
        if (out < 0) { ::close(in); return false; }
        bool ok = ::ioctl(out, FICLONE, in) == 0;
        ::close(in);
        ::close(out);
        if (!ok) ::unlink(dst.c_str());
        return ok;
#elif defined(__APPLE__)
        return ::clonefile(src.c_str(), dst.c_str(), 0) == 0;
#else
        (void)src; (void)dst;
        return false;
#endif
    }

    bool SnapshotTree(const ufs::path& src, const ufs::path& dst,
                      uint64_t& copied_bytes, uint64_t& inodes) {
        std::error_code ec;
        ufs::create_directories(dst, ec);
        if (ec) return false;
        if (++inodes > max_snapshot_inodes) return false;
        for (const auto& e : ufs::directory_iterator(src, ec)) {
            ufs::path child = dst / e.path().filename();
            auto st = e.symlink_status(ec);
            if (ec) return false;
            if (ufs::is_symlink(st)) {
                if (++inodes > max_snapshot_inodes) return false;
                ufs::copy_symlink(e.path(), child, ec);
                if (ec) return false;
            } else if (ufs::is_directory(st)) {
                if (!SnapshotTree(e.path(), child, copied_bytes, inodes)) return false;
            } else if (ufs::is_regular_file(st)) {
                if (!SnapshotFile(e.path(), child, copied_bytes, inodes)) return false;
            }
        }
        return true;
    }

    static bool RestoreFile(const ufs::path& snap, const ufs::path& orig) {
        std::error_code ec;
        ufs::copy_file(snap, orig, ufs::copy_options::overwrite_existing, ec);
        if (ec) return false;
        // copy_file preserves permissions; enforce explicitly for portability.
        auto st = ufs::status(snap, ec);
        if (!ec) ufs::permissions(orig, st.permissions(), ec);
        return true;
    }

    static bool RestoreTree(const ufs::path& snap, const ufs::path& orig, uint64_t& files) {
        std::error_code ec;
        for (const auto& e : ufs::directory_iterator(snap, ec)) {
            ufs::path child = orig / e.path().filename();
            auto st = e.symlink_status(ec);
            if (ec) return false;
            if (ufs::is_symlink(st)) {
                ufs::copy_symlink(e.path(), child, ec);
                if (ec) return false;
                ++files;
            } else if (ufs::is_directory(st)) {
                ufs::create_directories(child, ec);
                if (ec) return false;
                if (!RestoreTree(e.path(), child, files)) return false;
            } else if (ufs::is_regular_file(st)) {
                if (!RestoreFile(e.path(), child)) return false;
                ++files;
            }
        }
        return true;
    }

    static bool ReadManifest(const ufs::path& txnDir, UndoTransaction& t) {
        std::ifstream m(txnDir / "manifest", std::ios::binary);
        if (!m) return false;
        std::string line;
        if (!std::getline(m, line) || line != "neuroshell-undo v1") return false;
        t.dir = txnDir;
        while (std::getline(m, line)) {
            if (line == "complete") { t.complete = true; break; }
            size_t tab1 = line.find('\t');
            if (tab1 == std::string::npos) continue;
            std::string key = line.substr(0, tab1);
            std::string rest = line.substr(tab1 + 1);
            if (key == "id") t.id = rest;
            else if (key == "ts") t.ts = std::atof(rest.c_str());
            else if (key == "command") t.command = UndoUnescape(rest);
            else if (key == "cwd") t.cwd = UndoUnescape(rest);
            else if (key == "bytes") t.bytes = (uint64_t)std::strtoull(rest.c_str(), nullptr, 10);
            else if (key == "files") t.files = (uint64_t)std::strtoull(rest.c_str(), nullptr, 10);
            else if (key == "entry") {
                // entry\t<type>\t<snapshot_rel>\t<original>
                size_t tab2 = rest.find('\t');
                if (tab2 == std::string::npos || tab2 == 0) continue;
                size_t tab3 = rest.find('\t', tab2 + 1);
                if (tab3 == std::string::npos) continue;
                UndoEntry e;
                e.type = rest[0];
                e.snapshot_rel = UndoUnescape(rest.substr(tab2 + 1, tab3 - tab2 - 1));
                e.original = UndoUnescape(rest.substr(tab3 + 1));
                if (e.type == 'f' || e.type == 'd' || e.type == 'l')
                    t.entries.push_back(std::move(e));
            }
        }
        return !t.id.empty();
    }
};

} // namespace neuroshell
