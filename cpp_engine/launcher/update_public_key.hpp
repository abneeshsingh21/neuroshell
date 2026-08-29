// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// Build-time pinned Ed25519 public key for update-manifest verification.
//
// Provisioning (see docs/UPDATE_SECURITY.md for the full runbook):
//   1. Generate a keypair on an OFFLINE machine:
//        python3 scripts/sign_release.py keygen --out-dir /secure/offline/keys
//   2. Rebuild the client with the real key pinned:
//        cmake -DNEUROSHELL_UPDATE_PUBKEY=<64-hex-chars> ..
//      or edit kDefaultUpdatePublicKeyHex below before tagging a release.
//   3. Sign every release manifest with scripts/sign_release.py sign.
//
// FAIL-CLOSED BEHAVIOUR: while the placeholder (all-zero) key below is in
// effect, the self-updater REFUSES to install anything and tells the user
// to update through their package manager instead. An all-zero key is not
// a valid Ed25519 point, so even a logic bug elsewhere cannot cause a
// signature to verify against it.
#pragma once

namespace neuroshell::update {

// 32-byte Ed25519 public key, lowercase hex (64 chars).
#if defined(NEUROSHELL_UPDATE_PUBKEY)
#define NS_STRINGIFY_IMPL(x) #x
#define NS_STRINGIFY(x) NS_STRINGIFY_IMPL(x)
inline constexpr const char* kUpdatePublicKeyHex = NS_STRINGIFY(NEUROSHELL_UPDATE_PUBKEY);
#undef NS_STRINGIFY
#undef NS_STRINGIFY_IMPL
#else
// PLACEHOLDER — not a usable key. The verifier detects this exact value and
// disables self-update entirely (fail closed).
inline constexpr const char* kUpdatePublicKeyHex =
    "0000000000000000000000000000000000000000000000000000000000000000";
#endif

inline bool IsPlaceholderKey(const char* hex) {
    for (const char* p = hex; *p; ++p) {
        if (*p != '0') return false;
    }
    return true;
}

} // namespace neuroshell::update
