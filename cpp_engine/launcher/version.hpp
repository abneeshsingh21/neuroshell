// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// Single Source of Truth for the native host version.
// Keep in sync with: __version__.py, pyproject.toml (release tooling reads this header).
#pragma once

#include <string>
#include <vector>
#include <sstream>
#include <cctype>

#define NEUROSHELL_VERSION "5.18.0"
#define NEUROSHELL_VERSION_MAJOR 5
#define NEUROSHELL_VERSION_MINOR 18
#define NEUROSHELL_VERSION_PATCH 0

namespace neuroshell::version {

inline std::vector<long> ParseSemver(const std::string& v) {
    std::vector<long> parts;
    std::string cleaned = v;
    if (!cleaned.empty() && (cleaned[0] == 'v' || cleaned[0] == 'V')) cleaned.erase(0, 1);
    // Strip pre-release / build metadata ("5.8.0-rc.1+build" -> "5.8.0")
    size_t cut = cleaned.find_first_of("-+");
    if (cut != std::string::npos) cleaned = cleaned.substr(0, cut);

    std::stringstream ss(cleaned);
    std::string tok;
    while (std::getline(ss, tok, '.') && parts.size() < 4) {
        long val = 0;
        bool numeric = !tok.empty();
        for (char c : tok) {
            if (!std::isdigit(static_cast<unsigned char>(c))) { numeric = false; break; }
        }
        if (numeric) {
            try { val = std::stol(tok); } catch (...) { val = 0; }
        }
        parts.push_back(val);
    }
    while (parts.size() < 3) parts.push_back(0);
    return parts;
}

// Returns:  <0 if a < b,  0 if equal,  >0 if a > b   (numeric semver comparison,
// NOT lexicographic — "10.0.0" correctly compares greater than "5.8.0").
inline int CompareSemver(const std::string& a, const std::string& b) {
    std::vector<long> pa = ParseSemver(a);
    std::vector<long> pb = ParseSemver(b);
    for (size_t i = 0; i < 3; ++i) {
        if (pa[i] < pb[i]) return -1;
        if (pa[i] > pb[i]) return 1;
    }
    return 0;
}

// True when `remote` is a strictly newer release than the running build.
inline bool IsNewerRelease(const std::string& remote) {
    return CompareSemver(remote, NEUROSHELL_VERSION) > 0;
}

} // namespace neuroshell::version
