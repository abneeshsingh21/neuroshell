// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// HistoryEngine — SQLite+FTS5 command history with ranked recall
// (Phase 3 of the engineering roadmap).
//
// Replaces the append-only ~/.neuroshell/history.txt flat file with the
// SAME ~/.neuroshell/history.db the Python daemon already maintains
// (core/history.py): one unified history across both processes.
//
//   * WAL journal + busy_timeout → safe concurrent host/daemon access.
//   * Schema-compatible INSERTs into the existing `commands` table
//     (source='native_host') + `commands_fts` FTS5 index.
//   * Ranked recall (Ctrl+R and prompt history) scored as
//         0.6 · frecency  +  0.3 · cwd-affinity  +  0.1 · prefix-match
//     where frecency = ln(1+uses) · exp(-age_hours / 72) — frequently and
//     recently used commands surface first, commands run in the CURRENT
//     directory get a strong boost, and prefix matches beat substring hits.
//   * One-time migration: legacy history.txt lines are imported on first
//     open (marker row prevents re-import), the file is left untouched.
//   * Fail-open: if no system SQLite can be loaded (sqlite_dyn), every call
//     degrades to a no-op/empty result and the caller keeps the in-memory
//     session history — the shell never refuses to start.
//
// SECURITY: all user input is bound via prepared-statement parameters —
// nothing is ever concatenated into SQL. FTS queries are wrapped as quoted
// prefix tokens so FTS5 operators in user input are inert.
#pragma once

#include "sqlite_dyn.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <vector>

namespace neuroshell {

struct RankedCommand {
    std::string command;
    std::string cwd;      // most recent cwd it ran in
    double score = 0.0;
    int64_t uses = 0;
    int64_t last_ts = 0;  // unix seconds
};

class HistoryEngine {
public:
    static constexpr double kFrecencyWeight = 0.6;
    static constexpr double kCwdWeight = 0.3;
    static constexpr double kPrefixWeight = 0.1;
    static constexpr double kHalfLifeHours = 72.0; // 3-day decay half-life
    static constexpr int kBusyTimeoutMs = 5000;

    HistoryEngine() = default;
    ~HistoryEngine() { Close(); }
    HistoryEngine(const HistoryEngine&) = delete;
    HistoryEngine& operator=(const HistoryEngine&) = delete;

    // Open (creating schema if needed). Returns false when SQLite is
    // unavailable or the DB cannot be opened — callers fall back to the
    // legacy flat file in that case.
    bool Open(const std::filesystem::path& db_path) {
        std::lock_guard<std::mutex> lock(mu_);
        if (!sqlite::available()) return false;
        CloseLocked();

        std::error_code ec;
        std::filesystem::create_directories(db_path.parent_path(), ec);

        const auto& sq = sqlite::api();
        if (sq.open_v2(db_path.string().c_str(), &db_,
                       sqlite::OPEN_READWRITE | sqlite::OPEN_CREATE | sqlite::OPEN_FULLMUTEX,
                       nullptr) != sqlite::OK) {
            CloseLocked();
            return false;
        }
        sq.busy_timeout(db_, kBusyTimeoutMs);
        Exec("PRAGMA journal_mode=WAL");
        Exec("PRAGMA synchronous=NORMAL");

        // Minimal schema-compatible subset of core/history.py — CREATE IF
        // NOT EXISTS is a no-op when the daemon already made the full table.
        if (!Exec("CREATE TABLE IF NOT EXISTS commands ("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  "command TEXT NOT NULL,"
                  "exit_code INTEGER DEFAULT 0,"
                  "stdout_preview TEXT DEFAULT '',"
                  "stderr_preview TEXT DEFAULT '',"
                  "cwd TEXT DEFAULT '',"
                  "shell TEXT DEFAULT '',"
                  "duration_ms REAL DEFAULT 0,"
                  "timestamp REAL NOT NULL,"
                  "session_id TEXT DEFAULT '',"
                  "intent TEXT DEFAULT '',"
                  "source TEXT DEFAULT '',"
                  "context_hash TEXT DEFAULT '',"
                  "was_ai_translated INTEGER DEFAULT 0,"
                  "original_nl TEXT DEFAULT '',"
                  "tags TEXT DEFAULT '',"
                  "resources_json TEXT DEFAULT '',"
                  "pid INTEGER DEFAULT 0)")) {
            CloseLocked();
            return false;
        }
        Exec("CREATE INDEX IF NOT EXISTS idx_commands_timestamp ON commands(timestamp DESC)");
        Exec("CREATE INDEX IF NOT EXISTS idx_commands_cwd ON commands(cwd)");

        // FTS5 (optional — LIKE fallback keeps working without it)
        fts_ok_ = Exec("CREATE VIRTUAL TABLE IF NOT EXISTS commands_fts USING fts5("
                       "command, original_nl, cwd, tags,"
                       "content='commands', content_rowid='id')");
        open_ = true;
        return true;
    }

    bool IsOpen() const {
        std::lock_guard<std::mutex> lock(mu_);
        return open_;
    }

    std::string LibVersion() const {
        return sqlite::available() ? sqlite::api().libversion() : "";
    }

    // Record one executed command (host-side write path).
    bool Append(const std::string& command, const std::string& cwd, int exit_code = 0) {
        std::lock_guard<std::mutex> lock(mu_);
        if (!open_ || command.empty()) return false;

        sqlite::Stmt st;
        if (!st.prepare(db_, "INSERT INTO commands (command, exit_code, cwd, timestamp, source) "
                             "VALUES (?1, ?2, ?3, ?4, 'native_host')"))
            return false;
        st.bind(1, command);
        st.bind(2, exit_code);
        st.bind(3, cwd);
        // Fractional seconds (µs resolution) — matches Python time.time()
        // and keeps same-second appends strictly ordered.
        st.bind(4, NowUnixF());
        if (st.step() != sqlite::DONE) return false;

        if (fts_ok_) {
            int64_t rowid = sqlite::api().last_insert_rowid(db_);
            sqlite::Stmt fts;
            if (fts.prepare(db_, "INSERT INTO commands_fts(rowid, command, original_nl, cwd, tags) "
                                 "VALUES (?1, ?2, '', ?3, '')")) {
                fts.bind(1, rowid);
                fts.bind(2, command);
                fts.bind(3, cwd);
                fts.step(); // FTS failure is non-fatal
            }
        }
        return true;
    }

    // Newest-first unique commands for the Up-arrow ring (session start).
    std::vector<std::string> RecentUnique(int limit = 500) {
        std::lock_guard<std::mutex> lock(mu_);
        std::vector<std::string> out;
        if (!open_) return out;

        sqlite::Stmt st;
        if (!st.prepare(db_, "SELECT command, MAX(timestamp) AS ts FROM commands "
                             "GROUP BY command ORDER BY ts DESC LIMIT ?1"))
            return out;
        st.bind(1, limit);
        while (st.step() == sqlite::ROW) out.push_back(st.text(0));
        return out;
    }

    // Ranked recall: 0.6·frecency + 0.3·cwd-affinity + 0.1·prefix.
    // Empty query = "what do I run around here?" (pure frecency+cwd).
    std::vector<RankedCommand> Search(const std::string& query, const std::string& current_cwd,
                                      int limit = 8) {
        std::lock_guard<std::mutex> lock(mu_);
        std::vector<RankedCommand> out;
        if (!open_) return out;

        // Aggregate per distinct command over a bounded candidate window.
        // Candidate filter uses FTS5 prefix tokens when possible, else LIKE.
        std::string sql =
            "SELECT c.command,"
            "       COUNT(*) AS uses,"
            "       MAX(c.timestamp) AS last_ts,"
            "       SUM(CASE WHEN c.cwd = ?1 THEN 1 ELSE 0 END) AS cwd_hits,"
            "       MAX(CASE WHEN c.cwd = ?1 THEN c.timestamp ELSE 0 END) AS cwd_last,"
            "       (SELECT c2.cwd FROM commands c2 WHERE c2.command = c.command "
            "        ORDER BY c2.timestamp DESC LIMIT 1) AS recent_cwd "
            "FROM commands c ";
        bool used_fts = false;
        if (!query.empty()) {
            if (fts_ok_) {
                sql += "JOIN commands_fts f ON c.id = f.rowid "
                       "WHERE commands_fts MATCH ?2 ";
                used_fts = true;
            } else {
                sql += "WHERE c.command LIKE ?2 ESCAPE '\\' ";
            }
        }
        sql += "GROUP BY c.command ORDER BY last_ts DESC LIMIT 400";

        sqlite::Stmt st;
        if (!st.prepare(db_, sql)) {
            if (used_fts) {
                // Corrupt/legacy FTS index — retry once with LIKE.
                fts_ok_ = false;
                return SearchLikeLocked(query, current_cwd, limit);
            }
            return out;
        }
        st.bind(1, current_cwd);
        if (!query.empty()) {
            st.bind(2, used_fts ? FtsPrefixQuery(query) : LikePattern(query));
        }

        return RankRows(st, query, limit);
    }

    // Total stored rows (diagnostics / tests).
    int64_t Count() {
        std::lock_guard<std::mutex> lock(mu_);
        if (!open_) return -1;
        sqlite::Stmt st;
        if (!st.prepare(db_, "SELECT COUNT(*) FROM commands")) return -1;
        return st.step() == sqlite::ROW ? st.i64(0) : -1;
    }

    // One-time import of the legacy flat file. Uses a marker row so re-runs
    // are no-ops; the file itself is left in place (rollback safety).
    int MigrateLegacyFile(const std::filesystem::path& txt_path) {
        std::lock_guard<std::mutex> lock(mu_);
        if (!open_) return 0;

        {
            sqlite::Stmt probe;
            if (!probe.prepare(db_, "SELECT 1 FROM commands WHERE source = 'legacy_txt_migration' LIMIT 1"))
                return 0;
            if (probe.step() == sqlite::ROW) return 0; // already migrated
        }
        std::ifstream f(txt_path);
        if (!f) return 0;

        Exec("BEGIN IMMEDIATE");
        // Marker row (empty command is never surfaced by recall queries,
        // which skip blanks).
        Exec("INSERT INTO commands (command, timestamp, source) "
             "VALUES ('', strftime('%s','now'), 'legacy_txt_migration')");

        // Preserve relative order with 1-second spacing ending "now".
        std::vector<std::string> lines;
        std::string line;
        while (std::getline(f, line)) {
            if (!line.empty() && line.size() <= 4096) lines.push_back(line);
        }
        int64_t base = NowUnix() - static_cast<int64_t>(lines.size());
        int imported = 0;
        sqlite::Stmt st;
        if (st.prepare(db_, "INSERT INTO commands (command, cwd, timestamp, source) "
                            "VALUES (?1, '', ?2, 'legacy_txt_migration')")) {
            for (size_t i = 0; i < lines.size(); ++i) {
                sqlite::api().reset(st.raw());
                st.bind(1, lines[i]);
                st.bind(2, static_cast<double>(base + static_cast<int64_t>(i)));
                if (st.step() != sqlite::DONE) continue;
                ++imported;
                // Keep the FTS index in sync — without this, migrated
                // commands would be invisible to ranked search.
                if (fts_ok_) {
                    int64_t rowid = sqlite::api().last_insert_rowid(db_);
                    sqlite::Stmt fts;
                    if (fts.prepare(db_, "INSERT INTO commands_fts(rowid, command, original_nl, cwd, tags) "
                                         "VALUES (?1, ?2, '', '', '')")) {
                        fts.bind(1, rowid);
                        fts.bind(2, lines[i]);
                        fts.step();
                    }
                }
            }
        }
        Exec("COMMIT");
        return imported;
    }

    void Close() {
        std::lock_guard<std::mutex> lock(mu_);
        CloseLocked();
    }

    // ── scoring (exposed for tests) ──────────────────────────
    static double FrecencyScore(int64_t uses, int64_t last_ts, int64_t now) {
        if (uses <= 0) return 0.0;
        double age_hours = static_cast<double>(now - last_ts) / 3600.0;
        if (age_hours < 0) age_hours = 0;
        return std::log(1.0 + static_cast<double>(uses)) *
               std::exp(-age_hours * 0.6931471805599453 / kHalfLifeHours);
    }

    // Quote-wrapped FTS5 prefix query: `git pu` → `"git" "pu"*` — user text
    // can never smuggle FTS operators (AND/OR/NEAR/columns).
    static std::string FtsPrefixQuery(const std::string& q) {
        std::string out;
        std::string tok;
        auto flush = [&](bool last) {
            if (tok.empty()) return;
            if (!out.empty()) out += ' ';
            out += '"';
            out += tok;
            out += '"';
            if (last) out += '*';
            tok.clear();
        };
        for (char c : q) {
            if (c == ' ' || c == '\t') {
                flush(false);
            } else if (c != '"') { // strip quotes — they'd close our wrapper
                tok += c;
            }
        }
        flush(true);
        return out;
    }

    static std::string LikePattern(const std::string& q) {
        std::string out = "%";
        for (char c : q) {
            if (c == '%' || c == '_' || c == '\\') out += '\\';
            out += c;
        }
        out += '%';
        return out;
    }

private:
    static int64_t NowUnix() {
        return std::chrono::duration_cast<std::chrono::seconds>(
                   std::chrono::system_clock::now().time_since_epoch())
            .count();
    }

    static double NowUnixF() {
        return static_cast<double>(std::chrono::duration_cast<std::chrono::microseconds>(
                   std::chrono::system_clock::now().time_since_epoch())
                   .count()) / 1e6;
    }

    bool Exec(const char* sql) {
        return sqlite::api().exec(db_, sql, nullptr, nullptr, nullptr) == sqlite::OK;
    }

    std::vector<RankedCommand> SearchLikeLocked(const std::string& query,
                                                const std::string& current_cwd, int limit) {
        std::vector<RankedCommand> out;
        sqlite::Stmt st;
        if (!st.prepare(db_,
                        "SELECT c.command, COUNT(*) AS uses, MAX(c.timestamp) AS last_ts,"
                        "       SUM(CASE WHEN c.cwd = ?1 THEN 1 ELSE 0 END) AS cwd_hits,"
                        "       MAX(CASE WHEN c.cwd = ?1 THEN c.timestamp ELSE 0 END) AS cwd_last,"
                        "       (SELECT c2.cwd FROM commands c2 WHERE c2.command = c.command "
                        "        ORDER BY c2.timestamp DESC LIMIT 1) AS recent_cwd "
                        "FROM commands c WHERE c.command LIKE ?2 ESCAPE '\\' "
                        "GROUP BY c.command ORDER BY last_ts DESC LIMIT 400"))
            return out;
        st.bind(1, current_cwd);
        st.bind(2, LikePattern(query));
        return RankRows(st, query, limit);
    }

    std::vector<RankedCommand> RankRows(sqlite::Stmt& st, const std::string& query, int limit) {
        const int64_t now = NowUnix();
        std::vector<RankedCommand> scored;

        while (st.step() == sqlite::ROW) {
            RankedCommand rc;
            rc.command = st.text(0);
            if (rc.command.empty()) continue; // skip migration marker
            rc.uses = st.i64(1);
            rc.last_ts = static_cast<int64_t>(st.f64(2));
            int64_t cwd_hits = st.i64(3);
            rc.cwd = st.text(5);

            // frecency ∈ (0, ~ln(1+uses)] — normalize softly to [0,1]
            double frec = FrecencyScore(rc.uses, rc.last_ts, now);
            double frec_norm = frec / (frec + 1.0);

            // cwd affinity: share of uses in the current directory
            double cwd_aff = rc.uses > 0
                                 ? static_cast<double>(cwd_hits) / static_cast<double>(rc.uses)
                                 : 0.0;

            // prefix bonus: exact-prefix beats substring
            double prefix = (!query.empty() && rc.command.rfind(query, 0) == 0) ? 1.0 : 0.0;

            rc.score = kFrecencyWeight * frec_norm + kCwdWeight * cwd_aff +
                       kPrefixWeight * prefix;
            scored.push_back(std::move(rc));
        }

        std::sort(scored.begin(), scored.end(), [](const RankedCommand& a, const RankedCommand& b) {
            if (a.score != b.score) return a.score > b.score;
            return a.last_ts > b.last_ts; // stable tiebreak: most recent wins
        });
        if (static_cast<int>(scored.size()) > limit) scored.resize(static_cast<size_t>(limit));
        return scored;
    }

    void CloseLocked() {
        if (db_) {
            sqlite::api().close_v2(db_);
            db_ = nullptr;
        }
        open_ = false;
        fts_ok_ = false;
    }

    mutable std::mutex mu_;
    sqlite::sqlite3* db_ = nullptr;
    bool open_ = false;
    bool fts_ok_ = false;
};

} // namespace neuroshell
