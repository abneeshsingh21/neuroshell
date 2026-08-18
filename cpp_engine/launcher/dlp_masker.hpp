// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
#pragma once

#include <string>
#include <string_view>
#include <vector>
#include <regex>
#include <mutex>
#include <atomic>
#include <sstream>

namespace neuroshell {

enum class DLPRedactionStyle {
    BULLET_MASK,    // Replaces secret with ••••••••
    PEEK_EDGES,     // Keeps first 4 and last 4 chars (e.g. AKIA••••••••WXYZ)
    COLOR_BADGE     // Injects highlighted badge: [🔒 SECRET MASKED]
};

struct DLPPattern {
    std::string name;
    std::regex regex_pattern;
    DLPRedactionStyle default_style;
};

class DLPMasker {
private:
    std::vector<DLPPattern> patterns_;
    std::atomic<bool> enabled_{true};
    std::atomic<bool> unmasked_temporary_{false};
    mutable std::mutex dlp_mutex_;
    std::atomic<uint64_t> total_secrets_masked_{0};

    void init_patterns() {
        // 1. AWS Access Keys
        patterns_.push_back({
            "AWS Access Key ID",
            std::regex(R"(\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b)"),
            DLPRedactionStyle::PEEK_EDGES
        });

        // 2. GitHub Personal Access Tokens (Classic & Fine-Grained)
        patterns_.push_back({
            "GitHub Token",
            std::regex(R"(\b(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,255}\b)"),
            DLPRedactionStyle::PEEK_EDGES
        });
        patterns_.push_back({
            "GitHub Fine-Grained PAT",
            std::regex(R"(\bgithub_pat_[a-zA-Z0-9_]{82}\b)"),
            DLPRedactionStyle::PEEK_EDGES
        });

        // 3. High-Entropy LLM API Keys (OpenAI, Groq, Anthropic, Gemini)
        patterns_.push_back({
            "OpenAI API Key",
            std::regex(R"(\bsk-(?:proj-|svcacct-)?[a-zA-Z0-9_\-]{32,128}\b)"),
            DLPRedactionStyle::PEEK_EDGES
        });
        patterns_.push_back({
            "Groq API Key",
            std::regex(R"(\bgsk_[a-zA-Z0-9]{48,64}\b)"),
            DLPRedactionStyle::PEEK_EDGES
        });
        patterns_.push_back({
            "Anthropic API Key",
            std::regex(R"(\bsk-ant-[a-zA-Z0-9_\-]{40,128}\b)"),
            DLPRedactionStyle::PEEK_EDGES
        });

        // 4. JWT & Bearer Authorization Tokens
        patterns_.push_back({
            "JWT Bearer Token",
            std::regex(R"(Bearer\s+(eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+))"),
            DLPRedactionStyle::COLOR_BADGE
        });

        // 5. Database Connection URIs with Embedded Passwords
        patterns_.push_back({
            "Database Connection URI",
            std::regex(R"((postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://([^:]+):([^@]+)@)"),
            DLPRedactionStyle::COLOR_BADGE
        });

        // 6. RSA / SSH / EC Private Key Headers
        patterns_.push_back({
            "Private Key Block",
            std::regex(R"(-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH|PGP)?\s*PRIVATE KEY[^\r\n]*)"),
            DLPRedactionStyle::COLOR_BADGE
        });
    }

public:
    DLPMasker() {
        init_patterns();
    }

    void set_enabled(bool val) { enabled_.store(val, std::memory_order_relaxed); }
    bool is_enabled() const { return enabled_.load(std::memory_order_relaxed); }

    void toggle_unmask() {
        unmasked_temporary_.store(!unmasked_temporary_.load(std::memory_order_relaxed), std::memory_order_relaxed);
    }

    bool is_unmasked() const {
        return unmasked_temporary_.load(std::memory_order_relaxed);
    }

    uint64_t get_total_masked() const {
        return total_secrets_masked_.load(std::memory_order_relaxed);
    }

    // Fast-path zero-copy line filter
    std::string filter_stream(const std::string& input) {
        if (!enabled_.load(std::memory_order_relaxed) || unmasked_temporary_.load(std::memory_order_relaxed)) {
            return input;
        }

        // Quick heuristic check before executing heavy regex matches
        if (input.find("AKIA") == std::string::npos &&
            input.find("ghp_") == std::string::npos &&
            input.find("github_pat_") == std::string::npos &&
            input.find("sk-") == std::string::npos &&
            input.find("gsk_") == std::string::npos &&
            input.find("Bearer") == std::string::npos &&
            input.find("://") == std::string::npos &&
            input.find("PRIVATE KEY") == std::string::npos) {
            return input;
        }

        std::lock_guard<std::mutex> lock(dlp_mutex_);
        std::string result = input;

        for (const auto& pat : patterns_) {
            std::smatch match;
            std::string temp;
            auto it = result.cbegin();
            bool found_any = false;

            while (std::regex_search(it, result.cend(), match, pat.regex_pattern)) {
                found_any = true;
                total_secrets_masked_.fetch_add(1, std::memory_order_relaxed);
                temp.append(it, it + match.position(0));

                std::string secret = match.str(0);
                std::string replacement;

                if (pat.default_style == DLPRedactionStyle::PEEK_EDGES && secret.length() > 8) {
                    replacement = secret.substr(0, 4) + "\x1b[33m••••••••••••\x1b[0m" + secret.substr(secret.length() - 4);
                } else if (pat.default_style == DLPRedactionStyle::COLOR_BADGE) {
                    replacement = "\x1b[41;97;1m [🔒 " + pat.name + " REDACTED] \x1b[0m";
                } else {
                    replacement = "\x1b[33m••••••••••••••••\x1b[0m";
                }

                temp.append(replacement);
                it += match.position(0) + match.length(0);
            }

            if (found_any) {
                temp.append(it, result.cend());
                result = std::move(temp);
            }
        }

        return result;
    }
};

} // namespace neuroshell
