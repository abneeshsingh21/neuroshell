/*
 * NeuroShell C++ Performance Engine
 * Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
 * Proprietary and Confidential — see LICENSE.txt
 *
 * High-performance native implementations of:
 *   - FastParser:    Shell command tokenizer & parser
 *   - FuzzyMatcher:  Levenshtein distance with prefix/contains scoring
 *   - MarkovEngine:  O(1) hash-map backed command prediction
 *
 * Compiled via pybind11 into a Python-importable shared library.
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <string>
#include <vector>
#include <unordered_map>
#include <algorithm>
#include <regex>
#include <sstream>
#include <cctype>
#include <optional>
#include <numeric>

namespace py = pybind11;

// ═══════════════════════════════════════════════════════════════
//  ParsedCommand — structured result of command parsing
// ═══════════════════════════════════════════════════════════════

struct Redirect {
    int fd;
    std::string mode;   // "write", "append", "read"
    std::string target;
};

struct ParsedCommand {
    std::string program;
    std::vector<std::string> arguments;
    std::vector<std::string> flags;
    std::vector<std::string> pipes;
    std::vector<Redirect> redirects;
    bool is_compound   = false;
    bool is_background = false;
    std::vector<std::string> subcommands;
};


// ═══════════════════════════════════════════════════════════════
//  FastParser — sub-microsecond shell command parser
// ═══════════════════════════════════════════════════════════════

class FastParser {
public:
    ParsedCommand parse(const std::string& raw) const {
        ParsedCommand result;
        std::string command = trim(raw);
        if (command.empty()) return result;

        // ── Pipe detection ──
        if (command.find('|') != std::string::npos &&
            command.find("||") == std::string::npos) {
            result.pipes = split_by(command, '|');
            result.is_compound = true;
            parse_single(result.pipes[0], result);
            return result;
        }

        // ── Compound connectors (&&, ||, ;) ──
        static const std::vector<std::string> connectors = {"&&", "||", ";"};
        for (const auto& conn : connectors) {
            auto pos = command.find(conn);
            if (pos != std::string::npos) {
                result.subcommands = split_by_str(command, conn);
                result.is_compound = true;
                parse_single(result.subcommands[0], result);
                return result;
            }
        }

        // ── Single command ──
        parse_single(command, result);
        return result;
    }

private:
    void parse_single(const std::string& raw, ParsedCommand& result) const {
        std::string command = trim(raw);

        // Background check
        if (!command.empty() && command.back() == '&') {
            // Make sure it's not "&&"
            if (command.size() < 2 || command[command.size() - 2] != '&') {
                command.pop_back();
                command = trim(command);
                result.is_background = true;
            }
        }

        // Extract redirects
        extract_redirects(command, result.redirects);

        // Tokenize
        auto tokens = tokenize(command);
        if (tokens.empty()) return;

        result.program = tokens[0];
        for (size_t i = 1; i < tokens.size(); ++i) {
            if (!tokens[i].empty() && tokens[i][0] == '-') {
                result.flags.push_back(tokens[i]);
            } else {
                result.arguments.push_back(tokens[i]);
            }
        }
    }

    std::vector<std::string> tokenize(const std::string& command) const {
        std::vector<std::string> tokens;
        std::string current;
        bool in_single = false, in_double = false, escape_next = false;

        for (char ch : command) {
            if (escape_next) {
                current += ch;
                escape_next = false;
            } else if (ch == '\\') {
                escape_next = true;
            } else if (ch == '\'' && !in_double) {
                in_single = !in_single;
            } else if (ch == '"' && !in_single) {
                in_double = !in_double;
            } else if (ch == ' ' && !in_single && !in_double) {
                if (!current.empty()) {
                    tokens.push_back(current);
                    current.clear();
                }
            } else {
                current += ch;
            }
        }
        if (!current.empty()) tokens.push_back(current);
        return tokens;
    }

    void extract_redirects(std::string& command,
                           std::vector<Redirect>& redirects) const {
        std::regex pattern(R"((2?)(>>?|<)\s*(\S+))");
        std::smatch match;
        std::string cleaned;
        std::string remaining = command;

        while (std::regex_search(remaining, match, pattern)) {
            Redirect r;
            std::string fd_str = match[1].str();
            std::string op     = match[2].str();
            r.target = match[3].str();
            r.fd     = fd_str.empty() ? 1 : std::stoi(fd_str);
            r.mode   = (op == ">>") ? "append" : (op == "<") ? "read" : "write";
            redirects.push_back(r);
            cleaned += match.prefix().str();
            remaining = match.suffix().str();
        }
        cleaned += remaining;
        command = trim(cleaned);
    }

    // ── Utilities ──
    static std::string trim(const std::string& s) {
        auto start = s.find_first_not_of(" \t\r\n");
        if (start == std::string::npos) return "";
        auto end = s.find_last_not_of(" \t\r\n");
        return s.substr(start, end - start + 1);
    }

    static std::vector<std::string> split_by(const std::string& s, char delim) {
        std::vector<std::string> parts;
        std::istringstream stream(s);
        std::string part;
        while (std::getline(stream, part, delim)) {
            auto trimmed = trim(part);
            if (!trimmed.empty()) parts.push_back(trimmed);
        }
        return parts;
    }

    static std::vector<std::string> split_by_str(const std::string& s,
                                                  const std::string& delim) {
        std::vector<std::string> parts;
        size_t start = 0;
        size_t pos;
        while ((pos = s.find(delim, start)) != std::string::npos) {
            auto part = trim(s.substr(start, pos - start));
            if (!part.empty()) parts.push_back(part);
            start = pos + delim.size();
        }
        auto last = trim(s.substr(start));
        if (!last.empty()) parts.push_back(last);
        return parts;
    }
};


// ═══════════════════════════════════════════════════════════════
//  FuzzyMatcher — Levenshtein + prefix/contains scoring
// ═══════════════════════════════════════════════════════════════

class FuzzyMatcher {
public:
    FuzzyMatcher() = default;
    explicit FuzzyMatcher(const std::vector<std::string>& candidates)
        : candidates_(candidates) {}

    void set_candidates(const std::vector<std::string>& candidates) {
        candidates_ = candidates;
    }

    // Returns [(candidate, distance), ...] sorted by distance
    std::vector<std::pair<std::string, int>>
    match(const std::string& query, int max_distance = 3, int limit = 5) const {
        if (query.empty() || candidates_.empty()) return {};

        std::string q = to_lower(query);
        std::vector<std::pair<std::string, int>> scored;
        scored.reserve(candidates_.size());

        for (const auto& cand : candidates_) {
            std::string cl = to_lower(cand);

            // Exact prefix → distance 0
            if (cl.rfind(q, 0) == 0) {
                scored.emplace_back(cand, 0);
                continue;
            }
            // Contains → distance 1
            if (cl.find(q) != std::string::npos) {
                scored.emplace_back(cand, 1);
                continue;
            }
            // Levenshtein
            int dist = levenshtein(q, cl);
            if (dist <= max_distance) {
                scored.emplace_back(cand, dist);
            }
        }

        std::sort(scored.begin(), scored.end(),
                  [](const auto& a, const auto& b) { return a.second < b.second; });

        if (static_cast<int>(scored.size()) > limit)
            scored.resize(limit);
        return scored;
    }

    std::optional<std::string> best_match(const std::string& query,
                                           int max_distance = 3) const {
        auto matches = match(query, max_distance, 1);
        if (!matches.empty()) return matches[0].first;
        return std::nullopt;
    }

    std::optional<std::string> did_you_mean(const std::string& query) const {
        auto matches = match(query, 2, 1);
        if (!matches.empty() && matches[0].second > 0)
            return matches[0].first;
        return std::nullopt;
    }

    // Expose levenshtein publicly for benchmarking
    static int levenshtein(const std::string& s1, const std::string& s2) {
        const size_t m = s1.size(), n = s2.size();
        if (m == 0) return static_cast<int>(n);
        if (n == 0) return static_cast<int>(m);

        // Single-row DP for memory efficiency
        std::vector<int> prev(n + 1), curr(n + 1);
        std::iota(prev.begin(), prev.end(), 0);

        for (size_t i = 1; i <= m; ++i) {
            curr[0] = static_cast<int>(i);
            for (size_t j = 1; j <= n; ++j) {
                int cost = (s1[i - 1] == s2[j - 1]) ? 0 : 1;
                curr[j] = std::min({prev[j] + 1,       // deletion
                                    curr[j - 1] + 1,    // insertion
                                    prev[j - 1] + cost}); // substitution
            }
            std::swap(prev, curr);
        }
        return prev[n];
    }

private:
    std::vector<std::string> candidates_;

    static std::string to_lower(const std::string& s) {
        std::string result = s;
        std::transform(result.begin(), result.end(), result.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        return result;
    }
};


// ═══════════════════════════════════════════════════════════════
//  MarkovEngine — O(1) hash-map command prediction
// ═══════════════════════════════════════════════════════════════

class MarkovEngine {
public:
    void train(const std::vector<std::vector<std::string>>& sequences) {
        for (const auto& seq : sequences) {
            for (size_t i = 0; i + 1 < seq.size(); ++i) {
                transitions_[seq[i]][seq[i + 1]] += 1;
                totals_[seq[i]] += 1;
            }
        }
    }

    // Returns [(command, probability), ...] sorted by probability descending
    std::vector<std::pair<std::string, double>>
    predict(const std::string& current, int top_k = 3) const {
        auto it = transitions_.find(current);
        if (it == transitions_.end()) return {};

        int total = totals_.at(current);
        std::vector<std::pair<std::string, double>> predictions;
        predictions.reserve(it->second.size());

        for (const auto& [cmd, count] : it->second) {
            predictions.emplace_back(cmd,
                static_cast<double>(count) / static_cast<double>(total));
        }

        std::sort(predictions.begin(), predictions.end(),
                  [](const auto& a, const auto& b) { return a.second > b.second; });

        if (static_cast<int>(predictions.size()) > top_k)
            predictions.resize(top_k);

        // Round to 3 decimals
        for (auto& [cmd, prob] : predictions) {
            prob = static_cast<int>(prob * 1000.0 + 0.5) / 1000.0;
        }
        return predictions;
    }

    py::dict stats() const {
        int total_transitions = 0;
        for (const auto& [key, map] : transitions_) {
            total_transitions += static_cast<int>(map.size());
        }
        py::dict d;
        d["states"]      = static_cast<int>(transitions_.size());
        d["transitions"] = total_transitions;
        return d;
    }

private:
    std::unordered_map<std::string,
        std::unordered_map<std::string, int>> transitions_;
    std::unordered_map<std::string, int> totals_;
};


// ═══════════════════════════════════════════════════════════════
//  pybind11 module definition
// ═══════════════════════════════════════════════════════════════

PYBIND11_MODULE(cpp_engine_core, m) {
    m.doc() = "NeuroShell C++ Performance Engine — sub-microsecond "
              "command parsing, fuzzy matching, and Markov prediction.";

    // ── Redirect struct ──
    py::class_<Redirect>(m, "Redirect")
        .def(py::init<>())
        .def_readwrite("fd",     &Redirect::fd)
        .def_readwrite("mode",   &Redirect::mode)
        .def_readwrite("target", &Redirect::target);

    // ── ParsedCommand struct ──
    py::class_<ParsedCommand>(m, "ParsedCommand")
        .def(py::init<>())
        .def_readwrite("program",       &ParsedCommand::program)
        .def_readwrite("arguments",     &ParsedCommand::arguments)
        .def_readwrite("flags",         &ParsedCommand::flags)
        .def_readwrite("pipes",         &ParsedCommand::pipes)
        .def_readwrite("redirects",     &ParsedCommand::redirects)
        .def_readwrite("is_compound",   &ParsedCommand::is_compound)
        .def_readwrite("is_background", &ParsedCommand::is_background)
        .def_readwrite("subcommands",   &ParsedCommand::subcommands);

    // ── FastParser ──
    py::class_<FastParser>(m, "FastParser")
        .def(py::init<>())
        .def("parse", &FastParser::parse,
             py::arg("command"),
             "Parse a shell command string into a structured ParsedCommand.");

    // ── FuzzyMatcher ──
    py::class_<FuzzyMatcher>(m, "FuzzyMatcher")
        .def(py::init<>())
        .def(py::init<const std::vector<std::string>&>(),
             py::arg("candidates"))
        .def("set_candidates", &FuzzyMatcher::set_candidates,
             py::arg("candidates"))
        .def("match", &FuzzyMatcher::match,
             py::arg("query"),
             py::arg("max_distance") = 3,
             py::arg("limit") = 5,
             "Find closest matches. Returns [(candidate, distance), ...].")
        .def("best_match", &FuzzyMatcher::best_match,
             py::arg("query"),
             py::arg("max_distance") = 3,
             "Return the single best match, or None.")
        .def("did_you_mean", &FuzzyMatcher::did_you_mean,
             py::arg("query"),
             "Suggest a spelling correction, or None if exact match.")
        .def_static("levenshtein", &FuzzyMatcher::levenshtein,
                    py::arg("s1"), py::arg("s2"),
                    "Compute Levenshtein edit distance between two strings.");

    // ── MarkovEngine ──
    py::class_<MarkovEngine>(m, "MarkovEngine")
        .def(py::init<>())
        .def("train", &MarkovEngine::train,
             py::arg("sequences"),
             "Train from sequences of command strings.")
        .def("predict", &MarkovEngine::predict,
             py::arg("current"),
             py::arg("top_k") = 3,
             "Predict next commands with probabilities.")
        .def_property_readonly("stats", &MarkovEngine::stats,
             "Get engine statistics: {states, transitions}.");
}
