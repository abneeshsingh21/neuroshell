// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// json_mini — a small, hardened, allocation-conscious JSON reader.
//
// Purpose-built for parsing UNTRUSTED input (update manifests fetched over
// the network, daemon IPC responses). Hardening properties:
//   * strict RFC 8259 grammar (no comments, no trailing commas, no NaN/Inf),
//   * explicit recursion-depth cap (default 32) — stack exhaustion immune,
//   * input size cap enforced by the caller-facing Parse() API,
//   * full string-escape handling incl. \uXXXX with surrogate pairs → UTF-8,
//   * duplicate keys resolved as last-wins (documented, deterministic),
//   * numbers surfaced as both raw text and double; integer helper with
//     range checking,
//   * zero exceptions on the parse path — Parse() returns success/failure.
//
// This intentionally implements a READER, not a writer/DOM mutation API:
// the native host only ever consumes JSON produced by other components.
#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace neuroshell::json {

class Value;
using ValuePtr = std::shared_ptr<Value>;

enum class Type : uint8_t { Null, Bool, Number, String, Array, Object };

class Value {
public:
    Type type = Type::Null;
    bool bool_v = false;
    double num_v = 0.0;
    std::string raw_num;   // exact source text of the number
    std::string str_v;
    std::vector<ValuePtr> arr_v;
    std::map<std::string, ValuePtr> obj_v; // last-wins for duplicate keys

    bool IsNull() const { return type == Type::Null; }
    bool IsBool() const { return type == Type::Bool; }
    bool IsNumber() const { return type == Type::Number; }
    bool IsString() const { return type == Type::String; }
    bool IsArray() const { return type == Type::Array; }
    bool IsObject() const { return type == Type::Object; }

    // Object lookup; returns nullptr when absent or when *this isn't an object.
    const Value* Get(const std::string& key) const {
        if (type != Type::Object) return nullptr;
        auto it = obj_v.find(key);
        return it == obj_v.end() ? nullptr : it->second.get();
    }

    // Typed convenience accessors (nullptr-safe patterns at call sites).
    std::string GetString(const std::string& key, const std::string& fallback = "") const {
        const Value* v = Get(key);
        return (v && v->IsString()) ? v->str_v : fallback;
    }

    // Strict signed-integer accessor: requires an integral JSON number that
    // fits int64 exactly (no floats, no overflow truncation).
    bool GetInt64(const std::string& key, int64_t& out) const {
        const Value* v = Get(key);
        if (!v || !v->IsNumber()) return false;
        return v->AsInt64(out);
    }

    bool AsInt64(int64_t& out) const {
        if (!IsNumber() || raw_num.empty()) return false;
        // Reject anything with a fraction or exponent.
        for (char c : raw_num) {
            if (c == '.' || c == 'e' || c == 'E') return false;
        }
        errno = 0;
        char* end = nullptr;
        long long v = std::strtoll(raw_num.c_str(), &end, 10);
        if (errno != 0 || end == raw_num.c_str() || *end != '\0') return false;
        out = static_cast<int64_t>(v);
        return true;
    }
};

class Parser {
public:
    // Parse `input` (bounded by max_bytes) into a Value tree.
    // Returns nullptr on any syntax violation, depth breach, or size breach.
    static ValuePtr Parse(const std::string& input, size_t max_bytes = 4 * 1024 * 1024,
                          int max_depth = 32) {
        if (input.size() > max_bytes) return nullptr;
        Parser p(input, max_depth);
        p.skip_ws();
        ValuePtr v = p.parse_value(0);
        if (!v) return nullptr;
        p.skip_ws();
        if (p.pos_ != input.size()) return nullptr; // trailing garbage
        return v;
    }

private:
    const std::string& s_;
    size_t pos_ = 0;
    int max_depth_;

    Parser(const std::string& s, int max_depth) : s_(s), max_depth_(max_depth) {}

    bool eof() const { return pos_ >= s_.size(); }
    char peek() const { return s_[pos_]; }

    void skip_ws() {
        while (!eof()) {
            char c = s_[pos_];
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r') ++pos_;
            else break;
        }
    }

    bool consume_lit(const char* lit) {
        size_t len = std::strlen(lit);
        if (pos_ + len > s_.size()) return false;
        if (s_.compare(pos_, len, lit) != 0) return false;
        pos_ += len;
        return true;
    }

    ValuePtr parse_value(int depth) {
        if (depth > max_depth_ || eof()) return nullptr;
        char c = peek();
        switch (c) {
            case '{': return parse_object(depth);
            case '[': return parse_array(depth);
            case '"': return parse_string_value();
            case 't':
                if (consume_lit("true")) {
                    auto v = std::make_shared<Value>();
                    v->type = Type::Bool;
                    v->bool_v = true;
                    return v;
                }
                return nullptr;
            case 'f':
                if (consume_lit("false")) {
                    auto v = std::make_shared<Value>();
                    v->type = Type::Bool;
                    v->bool_v = false;
                    return v;
                }
                return nullptr;
            case 'n':
                if (consume_lit("null")) {
                    auto v = std::make_shared<Value>();
                    v->type = Type::Null;
                    return v;
                }
                return nullptr;
            default:
                if (c == '-' || (c >= '0' && c <= '9')) return parse_number();
                return nullptr;
        }
    }

    ValuePtr parse_object(int depth) {
        ++pos_; // '{'
        auto v = std::make_shared<Value>();
        v->type = Type::Object;
        skip_ws();
        if (!eof() && peek() == '}') { ++pos_; return v; }
        while (true) {
            skip_ws();
            if (eof() || peek() != '"') return nullptr;
            std::string key;
            if (!parse_string_raw(key)) return nullptr;
            skip_ws();
            if (eof() || peek() != ':') return nullptr;
            ++pos_;
            skip_ws();
            ValuePtr child = parse_value(depth + 1);
            if (!child) return nullptr;
            v->obj_v[key] = child; // duplicate keys: last-wins
            skip_ws();
            if (eof()) return nullptr;
            char c = peek();
            if (c == ',') { ++pos_; continue; }
            if (c == '}') { ++pos_; return v; }
            return nullptr;
        }
    }

    ValuePtr parse_array(int depth) {
        ++pos_; // '['
        auto v = std::make_shared<Value>();
        v->type = Type::Array;
        skip_ws();
        if (!eof() && peek() == ']') { ++pos_; return v; }
        while (true) {
            skip_ws();
            ValuePtr child = parse_value(depth + 1);
            if (!child) return nullptr;
            v->arr_v.push_back(child);
            skip_ws();
            if (eof()) return nullptr;
            char c = peek();
            if (c == ',') { ++pos_; continue; }
            if (c == ']') { ++pos_; return v; }
            return nullptr;
        }
    }

    ValuePtr parse_string_value() {
        auto v = std::make_shared<Value>();
        v->type = Type::String;
        if (!parse_string_raw(v->str_v)) return nullptr;
        return v;
    }

    static void append_utf8(std::string& out, uint32_t cp) {
        if (cp < 0x80) {
            out += static_cast<char>(cp);
        } else if (cp < 0x800) {
            out += static_cast<char>(0xC0 | (cp >> 6));
            out += static_cast<char>(0x80 | (cp & 0x3F));
        } else if (cp < 0x10000) {
            out += static_cast<char>(0xE0 | (cp >> 12));
            out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
            out += static_cast<char>(0x80 | (cp & 0x3F));
        } else {
            out += static_cast<char>(0xF0 | (cp >> 18));
            out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
            out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
            out += static_cast<char>(0x80 | (cp & 0x3F));
        }
    }

    bool parse_hex4(uint32_t& out) {
        if (pos_ + 4 > s_.size()) return false;
        uint32_t v = 0;
        for (int i = 0; i < 4; ++i) {
            char c = s_[pos_ + static_cast<size_t>(i)];
            v <<= 4;
            if (c >= '0' && c <= '9') v |= static_cast<uint32_t>(c - '0');
            else if (c >= 'a' && c <= 'f') v |= static_cast<uint32_t>(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') v |= static_cast<uint32_t>(c - 'A' + 10);
            else return false;
        }
        pos_ += 4;
        out = v;
        return true;
    }

    bool parse_string_raw(std::string& out) {
        if (eof() || peek() != '"') return false;
        ++pos_;
        out.clear();
        while (true) {
            if (eof()) return false;
            unsigned char c = static_cast<unsigned char>(s_[pos_]);
            if (c == '"') { ++pos_; return true; }
            if (c < 0x20) return false; // raw control chars are illegal
            if (c == '\\') {
                ++pos_;
                if (eof()) return false;
                char e = s_[pos_++];
                switch (e) {
                    case '"': out += '"'; break;
                    case '\\': out += '\\'; break;
                    case '/': out += '/'; break;
                    case 'b': out += '\b'; break;
                    case 'f': out += '\f'; break;
                    case 'n': out += '\n'; break;
                    case 'r': out += '\r'; break;
                    case 't': out += '\t'; break;
                    case 'u': {
                        uint32_t cp;
                        if (!parse_hex4(cp)) return false;
                        if (cp >= 0xD800 && cp <= 0xDBFF) {
                            // high surrogate — must be followed by \uDC00-\uDFFF
                            if (pos_ + 2 > s_.size() || s_[pos_] != '\\' || s_[pos_ + 1] != 'u')
                                return false;
                            pos_ += 2;
                            uint32_t lo;
                            if (!parse_hex4(lo)) return false;
                            if (lo < 0xDC00 || lo > 0xDFFF) return false;
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                        } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
                            return false; // lone low surrogate
                        }
                        append_utf8(out, cp);
                        break;
                    }
                    default:
                        return false;
                }
            } else {
                out += static_cast<char>(c);
                ++pos_;
            }
        }
    }

    ValuePtr parse_number() {
        size_t start = pos_;
        if (!eof() && peek() == '-') ++pos_;
        if (eof()) return nullptr;
        if (peek() == '0') {
            ++pos_;
        } else if (peek() >= '1' && peek() <= '9') {
            while (!eof() && peek() >= '0' && peek() <= '9') ++pos_;
        } else {
            return nullptr;
        }
        if (!eof() && peek() == '.') {
            ++pos_;
            if (eof() || peek() < '0' || peek() > '9') return nullptr;
            while (!eof() && peek() >= '0' && peek() <= '9') ++pos_;
        }
        if (!eof() && (peek() == 'e' || peek() == 'E')) {
            ++pos_;
            if (!eof() && (peek() == '+' || peek() == '-')) ++pos_;
            if (eof() || peek() < '0' || peek() > '9') return nullptr;
            while (!eof() && peek() >= '0' && peek() <= '9') ++pos_;
        }
        auto v = std::make_shared<Value>();
        v->type = Type::Number;
        v->raw_num = s_.substr(start, pos_ - start);
        errno = 0;
        v->num_v = std::strtod(v->raw_num.c_str(), nullptr);
        return v;
    }
};

} // namespace neuroshell::json
