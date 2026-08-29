// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// sqlite_dyn — runtime-loaded SQLite3 binding for the native host.
//
// Why runtime loading instead of linking (Phase 3 design decision):
//   * The host stays dependency-free at build time — same philosophy as the
//     embedded crypto (no OpenSSL) and the framework-free test suite. No
//     sqlite3.h, no vendored 9 MB amalgamation, no new link requirement.
//   * Every supported platform ships a system SQLite:
//       - Linux:   libsqlite3.so.0   (practically universal)
//       - macOS:   libsqlite3.dylib  (always, since 10.4)
//       - Windows: winsqlite3.dll    (System32, since Windows 10)
//   * If no library can be loaded the caller degrades gracefully to the
//     legacy flat-file history — the shell never refuses to start.
//
// Only the 20-function C API subset the history engine needs is bound. The
// sqlite3 C ABI is famously stable (frozen since 2004), which is what makes
// this safe; every symbol is resolved defensively and a single missing
// symbol marks the whole binding unavailable.
#pragma once

#include <cstdint>
#include <string>

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace neuroshell::sqlite {

// Opaque handle types (mirror the real ones — pointer-sized, never inspected)
struct sqlite3;
struct sqlite3_stmt;

// Result codes / flags actually used (values fixed by the SQLite ABI forever)
constexpr int OK = 0;
constexpr int ROW = 100;
constexpr int DONE = 101;
constexpr int OPEN_READWRITE = 0x00000002;
constexpr int OPEN_CREATE = 0x00000004;
constexpr int OPEN_FULLMUTEX = 0x00010000;

// SQLITE_TRANSIENT: tell sqlite to copy bound text immediately
using bind_destructor = void (*)(void*);
inline const bind_destructor TRANSIENT = reinterpret_cast<bind_destructor>(-1);

struct Api {
    int (*open_v2)(const char*, sqlite3**, int, const char*) = nullptr;
    int (*close_v2)(sqlite3*) = nullptr;
    int (*exec)(sqlite3*, const char*, int (*)(void*, int, char**, char**), void*, char**) = nullptr;
    int (*prepare_v2)(sqlite3*, const char*, int, sqlite3_stmt**, const char**) = nullptr;
    int (*step)(sqlite3_stmt*) = nullptr;
    int (*finalize)(sqlite3_stmt*) = nullptr;
    int (*reset)(sqlite3_stmt*) = nullptr;
    int (*bind_text)(sqlite3_stmt*, int, const char*, int, bind_destructor) = nullptr;
    int (*bind_int64)(sqlite3_stmt*, int, int64_t) = nullptr;
    int (*bind_double)(sqlite3_stmt*, int, double) = nullptr;
    int (*bind_int)(sqlite3_stmt*, int, int) = nullptr;
    const unsigned char* (*column_text)(sqlite3_stmt*, int) = nullptr;
    int64_t (*column_int64)(sqlite3_stmt*, int) = nullptr;
    double (*column_double)(sqlite3_stmt*, int) = nullptr;
    int (*column_int)(sqlite3_stmt*, int) = nullptr;
    const char* (*errmsg)(sqlite3*) = nullptr;
    const char* (*libversion)() = nullptr;
    int (*busy_timeout)(sqlite3*, int) = nullptr;
    int64_t (*last_insert_rowid)(sqlite3*) = nullptr;
    int (*changes)(sqlite3*) = nullptr;

    bool loaded = false;
};

namespace detail {

inline void* load_library() {
#if defined(_WIN32)
    // winsqlite3.dll ships in System32 on Windows 10+; sqlite3.dll covers
    // side-by-side installs.
    if (HMODULE h = LoadLibraryA("winsqlite3.dll")) return h;
    if (HMODULE h = LoadLibraryA("sqlite3.dll")) return h;
    return nullptr;
#else
    const char* candidates[] = {
#if defined(__APPLE__)
        "libsqlite3.dylib",
        "/usr/lib/libsqlite3.dylib",
#else
        "libsqlite3.so.0",
        "libsqlite3.so",
#endif
    };
    for (const char* name : candidates) {
        if (void* h = dlopen(name, RTLD_NOW | RTLD_LOCAL)) return h;
    }
    return nullptr;
#endif
}

inline void* resolve(void* lib, const char* name) {
#if defined(_WIN32)
    return reinterpret_cast<void*>(GetProcAddress(static_cast<HMODULE>(lib), name));
#else
    return dlsym(lib, name);
#endif
}

} // namespace detail

// Load and bind the API once per process (thread-safe magic static).
// Returns a reference whose .loaded flag reports availability.
inline const Api& api() {
    static const Api instance = [] {
        Api a;
        void* lib = detail::load_library();
        if (!lib) return a;

        bool ok = true;
        auto bind = [&](auto& fn, const char* name) {
            fn = reinterpret_cast<std::remove_reference_t<decltype(fn)>>(
                detail::resolve(lib, name));
            if (!fn) ok = false;
        };

        bind(a.open_v2, "sqlite3_open_v2");
        bind(a.close_v2, "sqlite3_close_v2");
        bind(a.exec, "sqlite3_exec");
        bind(a.prepare_v2, "sqlite3_prepare_v2");
        bind(a.step, "sqlite3_step");
        bind(a.finalize, "sqlite3_finalize");
        bind(a.reset, "sqlite3_reset");
        bind(a.bind_text, "sqlite3_bind_text");
        bind(a.bind_int64, "sqlite3_bind_int64");
        bind(a.bind_double, "sqlite3_bind_double");
        bind(a.bind_int, "sqlite3_bind_int");
        bind(a.column_text, "sqlite3_column_text");
        bind(a.column_int64, "sqlite3_column_int64");
        bind(a.column_double, "sqlite3_column_double");
        bind(a.column_int, "sqlite3_column_int");
        bind(a.errmsg, "sqlite3_errmsg");
        bind(a.libversion, "sqlite3_libversion");
        bind(a.busy_timeout, "sqlite3_busy_timeout");
        bind(a.last_insert_rowid, "sqlite3_last_insert_rowid");
        bind(a.changes, "sqlite3_changes");

        a.loaded = ok; // all-or-nothing: one missing symbol disables the binding
        return a;
    }();
    return instance;
}

inline bool available() { return api().loaded; }

// ── Thin RAII helpers ─────────────────────────────────────────

class Stmt {
public:
    Stmt() = default;
    ~Stmt() { finalize(); }
    Stmt(const Stmt&) = delete;
    Stmt& operator=(const Stmt&) = delete;

    bool prepare(sqlite3* db, const std::string& sql) {
        finalize();
        return api().prepare_v2(db, sql.c_str(), static_cast<int>(sql.size()), &stmt_, nullptr) == OK;
    }

    bool bind(int idx, const std::string& v) {
        return api().bind_text(stmt_, idx, v.data(), static_cast<int>(v.size()), TRANSIENT) == OK;
    }
    bool bind(int idx, int64_t v) { return api().bind_int64(stmt_, idx, v) == OK; }
    bool bind(int idx, double v) { return api().bind_double(stmt_, idx, v) == OK; }
    bool bind(int idx, int v) { return api().bind_int(stmt_, idx, v) == OK; }

    int step() { return stmt_ ? api().step(stmt_) : DONE; }

    std::string text(int col) const {
        const unsigned char* p = api().column_text(stmt_, col);
        return p ? reinterpret_cast<const char*>(p) : "";
    }
    int64_t i64(int col) const { return api().column_int64(stmt_, col); }
    double f64(int col) const { return api().column_double(stmt_, col); }
    int i32(int col) const { return api().column_int(stmt_, col); }

    void finalize() {
        if (stmt_) {
            api().finalize(stmt_);
            stmt_ = nullptr;
        }
    }

    sqlite3_stmt* raw() const { return stmt_; }

private:
    sqlite3_stmt* stmt_ = nullptr;
};

} // namespace neuroshell::sqlite
