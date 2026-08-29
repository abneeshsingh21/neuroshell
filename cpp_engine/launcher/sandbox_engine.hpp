// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// ═══════════════════════════════════════════════════════════════════
// Phase 8 (v5.16): Kernel-Level Sandboxing for AI-Generated Commands
// ═══════════════════════════════════════════════════════════════════
//
// The Phase 4 blast-radius preview is a heuristic net — obfuscated
// commands can evade string analysis. This module adds ENFORCEMENT:
// the kernel itself confines the child process, no matter what the
// command string turned out to mean.
//
// Linux implementation (applied in the child between fork and exec):
//   1. PR_SET_NO_NEW_PRIVS      — setuid/setgid/caps can never elevate.
//   2. Landlock LSM (ABI 1+)    — filesystem confinement:
//        • whole tree ("/"):    read + execute only
//        • project dir, /tmp, ~/.neuroshell: full read-write
//        → an AI-translated `rm` outside the project dir gets EACCES
//          from the KERNEL, not from a regex.
//   3. seccomp-BPF denylist    — kernel-surface hardening: mount family,
//        pivot_root/chroot, module load/unload, reboot/kexec, swap,
//        bpf(), open_by_handle_at (a classic Landlock bypass primitive),
//        perf_event_open. Denied calls fail with EPERM (readable errors,
//        not SIGKILL). Non-native-arch syscalls are killed outright so
//        the denylist cannot be side-stepped via the 32-bit compat table.
//
// Modes (roadmap: `sandbox: strict|project|off`):
//   off      — never sandbox.
//   project  — sandbox AI-TRANSLATED commands only (the untrusted input
//              path); commands the user typed verbatim run unconfined.
//   strict   — sandbox every non-TUI command.
//
// Escalation: `!command` runs one command unsandboxed (explicit user
// intent), mirroring sudo ergonomics.
//
// Non-Linux platforms compile to stubs that report "unsupported". On
// Linux, when confinement was requested but cannot be applied,
// ApplyInChild honors fail_closed and refuses to exec — a sandbox that
// silently isn't there is worse than an error.
//
// FORK-SAFETY CONTRACT: PreparedSandbox is fully built by the PARENT
// before fork (all allocation happens there); ApplyInChild performs only
// raw syscalls (prctl/landlock/seccomp/open/close) — no allocation.

#pragma once

#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#if defined(__linux__)
  #include <fcntl.h>
  #include <unistd.h>
  #include <sys/prctl.h>
  #include <sys/stat.h>
  #include <sys/syscall.h>
  #include <linux/audit.h>
  #include <linux/filter.h>
  #include <linux/seccomp.h>
  #if __has_include(<linux/landlock.h>)
    #include <linux/landlock.h>
    #define NEUROSHELL_HAS_LANDLOCK 1
  #endif
#endif

namespace neuroshell {

// ───────────────────────────────────────────────────────────
// Modes & policy
// ───────────────────────────────────────────────────────────

enum class SandboxMode { Off, Project, Strict };

inline const char* SandboxModeName(SandboxMode m) {
    switch (m) {
        case SandboxMode::Off:     return "off";
        case SandboxMode::Project: return "project";
        case SandboxMode::Strict:  return "strict";
    }
    return "off";
}

inline bool ParseSandboxMode(const std::string& s, SandboxMode& out) {
    if (s == "off")     { out = SandboxMode::Off;     return true; }
    if (s == "project") { out = SandboxMode::Project; return true; }
    if (s == "strict")  { out = SandboxMode::Strict;  return true; }
    return false;
}

// Decide whether a given execution should be confined.
//   aiTranslated — command came from NL translation (untrusted path)
//   escalated    — user prefixed `!` to run unsandboxed
inline bool ShouldSandbox(SandboxMode mode, bool aiTranslated, bool escalated) {
    if (escalated) return false;
    switch (mode) {
        case SandboxMode::Off:     return false;
        case SandboxMode::Project: return aiTranslated;
        case SandboxMode::Strict:  return true;
    }
    return false;
}

// ───────────────────────────────────────────────────────────
// Spec & support probe
// ───────────────────────────────────────────────────────────

struct SandboxSpec {
    bool enabled = false;
    bool fail_closed = true;              // can't confine ⇒ don't exec
    std::string project_dir;              // primary read-write root
    std::vector<std::string> rw_paths;    // extra RW roots (/tmp, ~/.neuroshell, …)
};

struct SandboxSupport {
    bool landlock = false;
    int  landlock_abi = 0;
    bool seccomp = false;
    std::string detail;
};

// Child-side failure step codes (distinct exit statuses for diagnosis).
enum SandboxApplyStep {
    SBX_OK = 0,
    SBX_ERR_NNP = 1,          // PR_SET_NO_NEW_PRIVS failed
    SBX_ERR_RULESET = 2,      // landlock_create_ruleset failed
    SBX_ERR_RULE = 3,         // landlock_add_rule failed
    SBX_ERR_RESTRICT = 4,     // landlock_restrict_self failed
    SBX_ERR_SECCOMP = 5,      // seccomp filter load failed
    SBX_ERR_UNSUPPORTED = 6,  // no landlock & fail_closed
};

#if defined(__linux__)

namespace sandbox_sys {
#ifdef NEUROSHELL_HAS_LANDLOCK
inline long landlock_create_ruleset(const struct landlock_ruleset_attr* attr,
                                    size_t size, uint32_t flags) {
    return syscall(SYS_landlock_create_ruleset, attr, size, flags);
}
inline long landlock_add_rule(int ruleset_fd, enum landlock_rule_type type,
                              const void* rule_attr, uint32_t flags) {
    return syscall(SYS_landlock_add_rule, ruleset_fd, type, rule_attr, flags);
}
inline long landlock_restrict_self(int ruleset_fd, uint32_t flags) {
    return syscall(SYS_landlock_restrict_self, ruleset_fd, flags);
}
#endif
inline long seccomp_load(unsigned int op, unsigned int flags, void* args) {
    return syscall(SYS_seccomp, op, flags, args);
}
} // namespace sandbox_sys

// ── Landlock access masks per ABI level ──

#ifdef NEUROSHELL_HAS_LANDLOCK
inline uint64_t LandlockFsRead() {
    return LANDLOCK_ACCESS_FS_EXECUTE |
           LANDLOCK_ACCESS_FS_READ_FILE |
           LANDLOCK_ACCESS_FS_READ_DIR;
}

inline uint64_t LandlockFsWrite(int abi) {
    uint64_t m = LANDLOCK_ACCESS_FS_WRITE_FILE |
                 LANDLOCK_ACCESS_FS_REMOVE_DIR |
                 LANDLOCK_ACCESS_FS_REMOVE_FILE |
                 LANDLOCK_ACCESS_FS_MAKE_CHAR |
                 LANDLOCK_ACCESS_FS_MAKE_DIR |
                 LANDLOCK_ACCESS_FS_MAKE_REG |
                 LANDLOCK_ACCESS_FS_MAKE_SOCK |
                 LANDLOCK_ACCESS_FS_MAKE_FIFO |
                 LANDLOCK_ACCESS_FS_MAKE_BLOCK |
                 LANDLOCK_ACCESS_FS_MAKE_SYM;
#ifdef LANDLOCK_ACCESS_FS_REFER
    if (abi >= 2) m |= LANDLOCK_ACCESS_FS_REFER;   // rename/link across dirs
#endif
#ifdef LANDLOCK_ACCESS_FS_TRUNCATE
    if (abi >= 3) m |= LANDLOCK_ACCESS_FS_TRUNCATE;
#endif
    return m;
}

// Landlock rejects rules that grant directory-only rights (MAKE_*,
// REMOVE_*, READ_DIR) on a non-directory fd — so file targets like
// /dev/null need a reduced mask.
inline uint64_t LandlockFsWriteFileOnly(int abi) {
    uint64_t m = LANDLOCK_ACCESS_FS_READ_FILE |
                 LANDLOCK_ACCESS_FS_WRITE_FILE;
#ifdef LANDLOCK_ACCESS_FS_TRUNCATE
    if (abi >= 3) m |= LANDLOCK_ACCESS_FS_TRUNCATE;
#endif
    (void)abi;
    return m;
}
#endif // NEUROSHELL_HAS_LANDLOCK

// ── Support probe (parent side) ──

inline SandboxSupport ProbeSandboxSupport() {
    SandboxSupport s;
#ifdef NEUROSHELL_HAS_LANDLOCK
    long abi = sandbox_sys::landlock_create_ruleset(
        nullptr, 0, LANDLOCK_CREATE_RULESET_VERSION);
    if (abi > 0) {
        s.landlock = true;
        s.landlock_abi = (int)abi;
    }
#endif
    errno = 0;
    long r = sandbox_sys::seccomp_load(SECCOMP_GET_ACTION_AVAIL, 0, nullptr);
    // With a null pointer: EFAULT ⇒ the seccomp syscall exists;
    // ENOSYS ⇒ it does not.
    s.seccomp = (r == 0) || (errno == EFAULT) || (errno == EINVAL);
    s.detail = std::string("landlock_abi=") + std::to_string(s.landlock_abi) +
               " seccomp=" + (s.seccomp ? "yes" : "no");
    return s;
}

// ── seccomp-BPF denylist ──

inline std::vector<int> SandboxDeniedSyscalls() {
    std::vector<int> v;
#ifdef SYS_mount
    v.push_back(SYS_mount);
#endif
#ifdef SYS_umount2
    v.push_back(SYS_umount2);
#endif
#ifdef SYS_pivot_root
    v.push_back(SYS_pivot_root);
#endif
#ifdef SYS_chroot
    v.push_back(SYS_chroot);
#endif
#ifdef SYS_init_module
    v.push_back(SYS_init_module);
#endif
#ifdef SYS_finit_module
    v.push_back(SYS_finit_module);
#endif
#ifdef SYS_delete_module
    v.push_back(SYS_delete_module);
#endif
#ifdef SYS_kexec_load
    v.push_back(SYS_kexec_load);
#endif
#ifdef SYS_kexec_file_load
    v.push_back(SYS_kexec_file_load);
#endif
#ifdef SYS_reboot
    v.push_back(SYS_reboot);
#endif
#ifdef SYS_swapon
    v.push_back(SYS_swapon);
#endif
#ifdef SYS_swapoff
    v.push_back(SYS_swapoff);
#endif
#ifdef SYS_bpf
    v.push_back(SYS_bpf);
#endif
#ifdef SYS_open_by_handle_at
    v.push_back(SYS_open_by_handle_at);
#endif
#ifdef SYS_perf_event_open
    v.push_back(SYS_perf_event_open);
#endif
#ifdef SYS_fsopen
    v.push_back(SYS_fsopen);
#endif
#ifdef SYS_fsmount
    v.push_back(SYS_fsmount);
#endif
#ifdef SYS_move_mount
    v.push_back(SYS_move_mount);
#endif
    return v;
}

#if defined(__x86_64__)
  #define NEUROSHELL_SECCOMP_ARCH AUDIT_ARCH_X86_64
#elif defined(__aarch64__)
  #define NEUROSHELL_SECCOMP_ARCH AUDIT_ARCH_AARCH64
#elif defined(__i386__)
  #define NEUROSHELL_SECCOMP_ARCH AUDIT_ARCH_I386
#else
  #define NEUROSHELL_SECCOMP_ARCH 0
#endif

// Built in the PARENT (allocates); the child only points a sock_fprog
// at the vector's data.
//
// Layout:
//   [0]      LD arch
//   [1]      JEQ native-arch ? +1 : +0
//   [2]      RET KILL_PROCESS            (wrong architecture)
//   [3]      LD nr
//   [4..4+n) JEQ denied[i] → jump to EPERM
//   [4+n]    RET ALLOW
//   [5+n]    RET ERRNO(EPERM)
inline sock_filter BpfStmt(uint16_t code, uint32_t k) {
    sock_filter s;
    s.code = code; s.jt = 0; s.jf = 0; s.k = k;
    return s;
}
inline sock_filter BpfJump(uint16_t code, uint32_t k, uint8_t jt, uint8_t jf) {
    sock_filter s;
    s.code = code; s.jt = jt; s.jf = jf; s.k = k;
    return s;
}

inline std::vector<sock_filter> BuildSeccompProgram() {
    std::vector<sock_filter> f;
    const std::vector<int> denied = SandboxDeniedSyscalls();
    const size_t n = denied.size();

    f.push_back(BpfStmt(BPF_LD | BPF_W | BPF_ABS,
                        (uint32_t)offsetof(struct seccomp_data, arch)));
    f.push_back(BpfJump(BPF_JMP | BPF_JEQ | BPF_K, NEUROSHELL_SECCOMP_ARCH, 1, 0));
    f.push_back(BpfStmt(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS));
    f.push_back(BpfStmt(BPF_LD | BPF_W | BPF_ABS,
                        (uint32_t)offsetof(struct seccomp_data, nr)));
    for (size_t i = 0; i < n; ++i) {
        // On match, skip the remaining (n-1-i) JEQs plus the ALLOW stmt.
        uint8_t jt = (uint8_t)((n - 1 - i) + 1);
        f.push_back(BpfJump(BPF_JMP | BPF_JEQ | BPF_K,
                            (uint32_t)denied[i], jt, 0));
    }
    f.push_back(BpfStmt(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
    f.push_back(BpfStmt(BPF_RET | BPF_K,
                        SECCOMP_RET_ERRNO | (EPERM & SECCOMP_RET_DATA)));
    return f;
}

// ───────────────────────────────────────────────────────────
// PreparedSandbox — parent builds, child applies
// ───────────────────────────────────────────────────────────

struct PreparedSandbox {
    bool enabled = false;
    bool fail_closed = true;
    bool landlock_available = false;
    int  landlock_abi = 0;
    std::vector<std::string> rw_paths;    // resolved, deduplicated
    std::vector<sock_filter> bpf;

    static PreparedSandbox Prepare(const SandboxSpec& spec) {
        PreparedSandbox p;
        p.enabled = spec.enabled;
        p.fail_closed = spec.fail_closed;
        if (!spec.enabled) return p;

        SandboxSupport sup = ProbeSandboxSupport();
        p.landlock_available = sup.landlock;
        p.landlock_abi = sup.landlock_abi;

        auto add_unique = [&p](const std::string& path) {
            if (path.empty()) return;
            for (const auto& e : p.rw_paths)
                if (e == path) return;
            p.rw_paths.push_back(path);
        };
        add_unique(spec.project_dir);
        for (const auto& e : spec.rw_paths) add_unique(e);
        // Device files every shell pipeline needs. These get a reduced
        // file-only mask in ApplyInChild (Landlock rejects directory
        // rights on non-directory fds).
        add_unique("/dev/null");
        add_unique("/dev/zero");
        add_unique("/dev/tty");
        add_unique("/dev/full");

        if (sup.seccomp) p.bpf = BuildSeccompProgram();
        return p;
    }

    // CHILD side: raw syscalls only. Returns SBX_OK or a step code.
    int ApplyInChild() const {
        if (!enabled) return SBX_OK;

        if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0)
            return SBX_ERR_NNP;

#ifdef NEUROSHELL_HAS_LANDLOCK
        if (landlock_available) {
            struct landlock_ruleset_attr attr;
            memset(&attr, 0, sizeof(attr));
            attr.handled_access_fs = LandlockFsRead() | LandlockFsWrite(landlock_abi);

            int ruleset_fd = (int)sandbox_sys::landlock_create_ruleset(
                &attr, sizeof(attr), 0);
            if (ruleset_fd < 0) return SBX_ERR_RULESET;

            // Whole tree: read + execute.
            {
                struct landlock_path_beneath_attr pb;
                memset(&pb, 0, sizeof(pb));
                pb.allowed_access = LandlockFsRead();
                pb.parent_fd = open("/", O_PATH | O_CLOEXEC);
                if (pb.parent_fd < 0) { close(ruleset_fd); return SBX_ERR_RULE; }
                long r = sandbox_sys::landlock_add_rule(
                    ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, &pb, 0);
                close(pb.parent_fd);
                if (r != 0) { close(ruleset_fd); return SBX_ERR_RULE; }
            }

            // RW roots: project dir + extras. Missing paths are skipped
            // (e.g. ~/.neuroshell on a fresh machine) — they'd be
            // unwritable anyway, which is the safe direction. Directories
            // get the full write mask; files (/dev/null, /dev/tty, …) get
            // a file-only mask because Landlock rejects directory rights
            // (MAKE_*, REMOVE_*, READ_DIR) on non-directory fds.
            for (const auto& path : rw_paths) {
                struct landlock_path_beneath_attr pb;
                memset(&pb, 0, sizeof(pb));
                pb.parent_fd = open(path.c_str(), O_PATH | O_CLOEXEC);
                if (pb.parent_fd < 0) continue;
                struct stat st;
                if (fstat(pb.parent_fd, &st) == 0 && S_ISDIR(st.st_mode)) {
                    pb.allowed_access = LandlockFsRead() | LandlockFsWrite(landlock_abi);
                } else {
                    pb.allowed_access = LandlockFsWriteFileOnly(landlock_abi);
                }
                long r = sandbox_sys::landlock_add_rule(
                    ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, &pb, 0);
                close(pb.parent_fd);
                if (r != 0) { close(ruleset_fd); return SBX_ERR_RULE; }
            }

            if (sandbox_sys::landlock_restrict_self(ruleset_fd, 0) != 0) {
                close(ruleset_fd);
                return SBX_ERR_RESTRICT;
            }
            close(ruleset_fd);
        } else if (fail_closed) {
            return SBX_ERR_UNSUPPORTED;
        }
#else
        if (fail_closed) return SBX_ERR_UNSUPPORTED;
#endif

        // seccomp last: it must not interfere with landlock syscalls above.
        if (!bpf.empty()) {
            struct sock_fprog prog;
            prog.len = (unsigned short)bpf.size();
            prog.filter = const_cast<sock_filter*>(bpf.data());
            if (sandbox_sys::seccomp_load(SECCOMP_SET_MODE_FILTER, 0, &prog) != 0)
                return SBX_ERR_SECCOMP;
        }
        return SBX_OK;
    }
};

#else  // ── non-Linux stubs ─────────────────────────────────

inline SandboxSupport ProbeSandboxSupport() {
    SandboxSupport s;
    s.detail = "kernel sandboxing unsupported on this platform";
    return s;
}

struct PreparedSandbox {
    bool enabled = false;
    bool fail_closed = true;
    bool landlock_available = false;
    int  landlock_abi = 0;
    std::vector<std::string> rw_paths;

    static PreparedSandbox Prepare(const SandboxSpec& spec) {
        PreparedSandbox p;
        p.enabled = spec.enabled;
        p.fail_closed = spec.fail_closed;
        return p;
    }
    int ApplyInChild() const {
        if (!enabled) return SBX_OK;
        return fail_closed ? SBX_ERR_UNSUPPORTED : SBX_OK;
    }
};

#endif // __linux__

inline const char* SandboxStepName(int step) {
    switch (step) {
        case SBX_OK:              return "ok";
        case SBX_ERR_NNP:         return "no_new_privs failed";
        case SBX_ERR_RULESET:     return "landlock ruleset creation failed";
        case SBX_ERR_RULE:        return "landlock rule installation failed";
        case SBX_ERR_RESTRICT:    return "landlock restrict_self failed";
        case SBX_ERR_SECCOMP:     return "seccomp filter load failed";
        case SBX_ERR_UNSUPPORTED: return "kernel sandboxing unavailable";
    }
    return "unknown";
}

} // namespace neuroshell
