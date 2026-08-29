// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// UpdateVerifier — the trust boundary of the self-update pipeline.
//
// Everything that arrives from the network is UNTRUSTED until this class
// says otherwise. Verification order (each step fails closed):
//
//   0. Key policy      — refuse everything if the pinned public key is the
//                        unprovisioned placeholder.
//   1. Signature       — Ed25519 over the RAW manifest bytes (not a re-
//                        serialization: no canonicalization ambiguity).
//   2. Schema          — strict JSON parse (json_mini) + required fields.
//   3. Anti-downgrade  — manifest version must be strictly newer than the
//                        running build (numeric semver), and the running
//                        build must satisfy min_version.
//   4. Freshness       — reject manifests past their expires_at (blocks
//                        indefinite replay of old signed manifests).
//   5. Artifact policy — platform match, https-only URL on an allowlisted
//                        host, sane size bounds, well-formed sha256.
//   6. Payload         — after download, the artifact's SHA-256 must equal
//                        the manifest's pinned digest (constant-time cmp).
//
// The signature covers the manifest, and the manifest pins the artifact
// digest, so a CDN or mirror can be fully hostile without being able to
// serve a modified binary.
#pragma once

#include "crypto/ed25519.hpp"
#include "crypto/sha2.hpp"
#include "json_mini.hpp"
#include "update_public_key.hpp"
#include "version.hpp"

#include <cstdint>
#include <ctime>
#include <fstream>
#include <string>
#include <vector>

namespace neuroshell::update {

struct ArtifactInfo {
    std::string platform;   // e.g. "linux-x86_64", "windows-x86_64", "macos-arm64"
    std::string name;       // file name, e.g. "neuroshell"
    std::string sha256;     // 64 lowercase hex chars
    int64_t size = 0;       // exact byte size
    std::string url;        // https download URL on an allowlisted host
};

struct VerifiedManifest {
    std::string version;    // e.g. "5.9.0"
    int64_t created_at = 0; // unix seconds
    int64_t expires_at = 0; // unix seconds
    std::string min_version;
    ArtifactInfo artifact;  // the artifact matching this build's platform
};

enum class VerifyStatus {
    Ok = 0,
    KeyNotProvisioned,
    BadSignature,
    MalformedManifest,
    UnsupportedSchema,
    Expired,
    NotYetValid,
    Downgrade,
    BelowMinVersion,
    NoArtifactForPlatform,
    BadArtifactUrl,
    BadArtifactDigestFormat,
    BadArtifactSize,
};

inline const char* VerifyStatusMessage(VerifyStatus s) {
    switch (s) {
        case VerifyStatus::Ok: return "ok";
        case VerifyStatus::KeyNotProvisioned:
            return "self-update disabled: no release signing key is provisioned in this build";
        case VerifyStatus::BadSignature:
            return "manifest signature verification FAILED — refusing update";
        case VerifyStatus::MalformedManifest:
            return "update manifest is malformed — refusing update";
        case VerifyStatus::UnsupportedSchema:
            return "update manifest schema version is not supported by this client";
        case VerifyStatus::Expired:
            return "update manifest has expired (possible replay of an old release) — refusing update";
        case VerifyStatus::NotYetValid:
            return "update manifest is dated in the future — clock skew or tampering, refusing update";
        case VerifyStatus::Downgrade:
            return "update manifest offers an older or equal version — downgrade refused";
        case VerifyStatus::BelowMinVersion:
            return "this installation is too old for in-place update; please reinstall from the official source";
        case VerifyStatus::NoArtifactForPlatform:
            return "no signed artifact published for this platform";
        case VerifyStatus::BadArtifactUrl:
            return "artifact URL violates the download policy (https + allowlisted host required)";
        case VerifyStatus::BadArtifactDigestFormat:
            return "artifact digest in manifest is malformed — refusing update";
        case VerifyStatus::BadArtifactSize:
            return "artifact size in manifest is outside sane bounds — refusing update";
    }
    return "unknown verification error";
}

class UpdateVerifier {
public:
    static constexpr int64_t kMaxArtifactBytes = 512LL * 1024 * 1024; // 512 MiB hard cap
    static constexpr int64_t kMinArtifactBytes = 64 * 1024;           // no 3-byte "binaries"
    static constexpr size_t kMaxManifestBytes = 256 * 1024;
    static constexpr int64_t kClockSkewSlackSecs = 24 * 3600; // tolerate ±1 day skew

    explicit UpdateVerifier(std::string pubkey_hex = kUpdatePublicKeyHex,
                            std::string running_version = NEUROSHELL_VERSION)
        : pubkey_hex_(std::move(pubkey_hex)), running_version_(std::move(running_version)) {}

    // The platform tag this build downloads artifacts for.
    static std::string CurrentPlatformTag() {
#if defined(_WIN32)
        const char* os = "windows";
#elif defined(__APPLE__)
        const char* os = "macos";
#else
        const char* os = "linux";
#endif
#if defined(__aarch64__) || defined(_M_ARM64)
        const char* arch = "arm64";
#else
        const char* arch = "x86_64";
#endif
        return std::string(os) + "-" + arch;
    }

    // Verify a raw manifest + detached hex signature. On success fills `out`.
    VerifyStatus VerifyManifest(const std::string& manifest_raw, const std::string& sig_hex,
                                VerifiedManifest& out, int64_t now_unix = -1,
                                const std::string& platform_tag = CurrentPlatformTag()) const {
        if (now_unix < 0) now_unix = static_cast<int64_t>(std::time(nullptr));

        // 0. Fail closed on unprovisioned key.
        if (IsPlaceholderKey(pubkey_hex_.c_str()) || pubkey_hex_.size() != 64)
            return VerifyStatus::KeyNotProvisioned;

        // 1. Signature over the RAW bytes — before any parsing of attacker
        //    input beyond what the (hardened) verifier itself touches.
        if (manifest_raw.empty() || manifest_raw.size() > kMaxManifestBytes)
            return VerifyStatus::MalformedManifest;
        if (!crypto::Ed25519::VerifyHex(
                sig_hex, reinterpret_cast<const uint8_t*>(manifest_raw.data()),
                manifest_raw.size(), pubkey_hex_))
            return VerifyStatus::BadSignature;

        // 2. Strict parse + schema checks.
        auto root = json::Parser::Parse(manifest_raw, kMaxManifestBytes);
        if (!root || !root->IsObject()) return VerifyStatus::MalformedManifest;

        int64_t schema = 0;
        if (!root->GetInt64("schema", schema) || schema != 1)
            return VerifyStatus::UnsupportedSchema;

        VerifiedManifest m;
        m.version = root->GetString("version");
        m.min_version = root->GetString("min_version", "0.0.0");
        if (m.version.empty() || !LooksLikeSemver(m.version))
            return VerifyStatus::MalformedManifest;
        if (!root->GetInt64("created_at", m.created_at) ||
            !root->GetInt64("expires_at", m.expires_at))
            return VerifyStatus::MalformedManifest;
        if (m.created_at <= 0 || m.expires_at <= m.created_at)
            return VerifyStatus::MalformedManifest;

        // 3. Anti-downgrade / floor version.
        if (version::CompareSemver(m.version, running_version_) <= 0)
            return VerifyStatus::Downgrade;
        if (version::CompareSemver(running_version_, m.min_version) < 0)
            return VerifyStatus::BelowMinVersion;

        // 4. Freshness window.
        if (now_unix > m.expires_at) return VerifyStatus::Expired;
        if (now_unix + kClockSkewSlackSecs < m.created_at) return VerifyStatus::NotYetValid;

        // 5. Artifact policy.
        const json::Value* arts = root->Get("artifacts");
        if (!arts || !arts->IsArray() || arts->arr_v.empty())
            return VerifyStatus::MalformedManifest;

        const json::Value* match = nullptr;
        for (const auto& a : arts->arr_v) {
            if (a->IsObject() && a->GetString("platform") == platform_tag) {
                match = a.get();
                break;
            }
        }
        if (!match) return VerifyStatus::NoArtifactForPlatform;

        m.artifact.platform = platform_tag;
        m.artifact.name = match->GetString("name");
        m.artifact.sha256 = match->GetString("sha256");
        m.artifact.url = match->GetString("url");
        if (!match->GetInt64("size", m.artifact.size))
            return VerifyStatus::MalformedManifest;

        if (m.artifact.name.empty() || !SafeFileName(m.artifact.name))
            return VerifyStatus::MalformedManifest;
        if (!ValidSha256Hex(m.artifact.sha256))
            return VerifyStatus::BadArtifactDigestFormat;
        if (m.artifact.size < kMinArtifactBytes || m.artifact.size > kMaxArtifactBytes)
            return VerifyStatus::BadArtifactSize;
        if (!UrlAllowed(m.artifact.url))
            return VerifyStatus::BadArtifactUrl;

        out = m;
        return VerifyStatus::Ok;
    }

    // Step 6: after download, bind the payload to the manifest digest.
    static bool VerifyArtifactFile(const std::string& path, const ArtifactInfo& art,
                                   std::string* err = nullptr) {
        std::ifstream f(path, std::ios::binary);
        if (!f) {
            if (err) *err = "cannot open downloaded artifact";
            return false;
        }
        crypto::SHA256 h;
        char buf[64 * 1024];
        int64_t total = 0;
        while (f) {
            f.read(buf, sizeof(buf));
            std::streamsize got = f.gcount();
            if (got > 0) {
                h.Update(buf, static_cast<size_t>(got));
                total += got;
                if (total > kMaxArtifactBytes) {
                    if (err) *err = "artifact exceeds maximum allowed size";
                    return false;
                }
            }
        }
        if (total != art.size) {
            if (err) *err = "artifact size mismatch (expected " + std::to_string(art.size) +
                            " bytes, got " + std::to_string(total) + ")";
            return false;
        }
        uint8_t digest[32];
        h.Final(digest);
        uint8_t expected[32];
        if (!crypto::FromHex(art.sha256, expected, sizeof(expected))) {
            if (err) *err = "manifest digest is not valid hex";
            return false;
        }
        if (!crypto::ConstantTimeEqual(digest, expected, 32)) {
            if (err) *err = "artifact SHA-256 mismatch — the download does not match the signed manifest";
            return false;
        }
        return true;
    }

    // Download policy: https only, exact-match host allowlist, no userinfo
    // trickery, no embedded whitespace/control chars.
    static bool UrlAllowed(const std::string& url) {
        static const char* kAllowedHosts[] = {
            "github.com",
            "objects.githubusercontent.com",
            "release-assets.githubusercontent.com",
        };
        const std::string scheme = "https://";
        if (url.size() < scheme.size() + 1 || url.compare(0, scheme.size(), scheme) != 0)
            return false;
        for (unsigned char c : url) {
            if (c <= 0x20 || c >= 0x7F) return false; // spaces / control / non-ASCII
        }
        size_t host_start = scheme.size();
        size_t host_end = url.find('/', host_start);
        if (host_end == std::string::npos) return false; // require a path
        std::string authority = url.substr(host_start, host_end - host_start);
        // Reject userinfo ("user@host") and explicit ports.
        if (authority.find('@') != std::string::npos) return false;
        if (authority.find(':') != std::string::npos) return false;
        if (authority.empty()) return false;
        // Lowercase for comparison (hosts are case-insensitive).
        for (auto& c : authority) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        for (const char* h : kAllowedHosts) {
            if (authority == h) return true;
        }
        return false;
    }

    static bool ValidSha256Hex(const std::string& s) {
        if (s.size() != 64) return false;
        for (char c : s) {
            bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
            if (!ok) return false; // lowercase only: canonical form
        }
        return true;
    }

    // Artifact names must be plain file names — no separators, no traversal.
    static bool SafeFileName(const std::string& n) {
        if (n.empty() || n.size() > 128) return false;
        if (n == "." || n == "..") return false;
        for (unsigned char c : n) {
            bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                      (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_';
            if (!ok) return false;
        }
        return true;
    }

    static bool LooksLikeSemver(const std::string& v) {
        int dots = 0;
        bool digit_seen = false;
        for (char c : v) {
            if (c >= '0' && c <= '9') { digit_seen = true; continue; }
            if (c == '.') { ++dots; continue; }
            return false; // release manifests carry plain x.y.z only
        }
        return digit_seen && dots == 2;
    }

private:
    std::string pubkey_hex_;
    std::string running_version_;
};

} // namespace neuroshell::update
