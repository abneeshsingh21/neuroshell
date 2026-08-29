// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// SHA-256 / SHA-512 — dependency-free implementations for the native host.
//
// Design notes (v5.9 update-security work):
//   * Round constants and initial hash values are NOT hand-typed hex tables —
//     they are derived at first use from their mathematical definition
//     (fractional bits of square/cube roots of the first primes) using exact
//     integer nth-root arithmetic on a tiny local bignum. A single-character
//     typo in a constants table is one of the classic ways a hash
//     implementation silently diverges; deriving them makes that class of
//     bug structurally impossible.
//   * Correctness is proven by cross-implementation test vectors generated
//     with Python `hashlib` (see cpp_engine/tests/crypto_tests.cpp).
//   * Streaming API (Init/Update/Final) + one-shot helpers.
//   * No heap allocation on the hot path; suitable for hashing large release
//     artifacts in fixed-size chunks.
#pragma once

#include <array>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace neuroshell::crypto {

// ─────────────────────────────────────────────────────────────
// detail: exact integer arithmetic to derive the SHA-2 constants
// ─────────────────────────────────────────────────────────────
namespace sha2_detail {

// Minimal unsigned bignum (little-endian 32-bit limbs). Only what the
// constant derivation needs: compare, subtract, shift-left, multiply.
struct BigNum {
    std::vector<uint32_t> limb; // little-endian

    static BigNum from_u64(uint64_t v) {
        BigNum b;
        b.limb.push_back(static_cast<uint32_t>(v));
        b.limb.push_back(static_cast<uint32_t>(v >> 32));
        b.trim();
        return b;
    }

    void trim() {
        while (limb.size() > 1 && limb.back() == 0) limb.pop_back();
        if (limb.empty()) limb.push_back(0);
    }

    static int cmp(const BigNum& a, const BigNum& b) {
        if (a.limb.size() != b.limb.size())
            return a.limb.size() < b.limb.size() ? -1 : 1;
        for (size_t i = a.limb.size(); i-- > 0;) {
            if (a.limb[i] != b.limb[i]) return a.limb[i] < b.limb[i] ? -1 : 1;
        }
        return 0;
    }

    static BigNum mul(const BigNum& a, const BigNum& b) {
        BigNum r;
        r.limb.assign(a.limb.size() + b.limb.size(), 0);
        for (size_t i = 0; i < a.limb.size(); ++i) {
            uint64_t carry = 0;
            for (size_t j = 0; j < b.limb.size(); ++j) {
                uint64_t cur = static_cast<uint64_t>(a.limb[i]) * b.limb[j] +
                               r.limb[i + j] + carry;
                r.limb[i + j] = static_cast<uint32_t>(cur);
                carry = cur >> 32;
            }
            size_t k = i + b.limb.size();
            while (carry) {
                uint64_t cur = static_cast<uint64_t>(r.limb[k]) + carry;
                r.limb[k] = static_cast<uint32_t>(cur);
                carry = cur >> 32;
                ++k;
            }
        }
        r.trim();
        return r;
    }

    static BigNum shl(const BigNum& a, unsigned bits) {
        BigNum r = a;
        unsigned words = bits / 32;
        unsigned rem = bits % 32;
        if (rem) {
            uint32_t carry = 0;
            for (auto& l : r.limb) {
                uint32_t nc = l >> (32 - rem);
                l = (l << rem) | carry;
                carry = nc;
            }
            if (carry) r.limb.push_back(carry);
        }
        r.limb.insert(r.limb.begin(), words, 0);
        r.trim();
        return r;
    }

    // Lowest 64 bits of the value.
    uint64_t low64() const {
        uint64_t v = limb[0];
        if (limb.size() > 1) v |= static_cast<uint64_t>(limb[1]) << 32;
        return v;
    }
};

// floor(N^(1/root)) via binary search on the bit-length of the result.
inline BigNum integer_nth_root(const BigNum& n, unsigned root) {
    // Upper bound: 2^(ceil(bits/root))
    size_t bits = n.limb.size() * 32;
    BigNum lo = BigNum::from_u64(0);
    BigNum hi = BigNum::shl(BigNum::from_u64(1), static_cast<unsigned>(bits / root + 2));

    // Binary search: largest x with x^root <= n
    while (true) {
        // mid = (lo + hi + 1) / 2  — implement via add + shift-right-1
        BigNum sum;
        {
            const BigNum& a = lo;
            const BigNum& b = hi;
            size_t sz = std::max(a.limb.size(), b.limb.size()) + 1;
            sum.limb.assign(sz, 0);
            uint64_t carry = 1; // the "+1" for ceiling midpoint
            for (size_t i = 0; i < sz; ++i) {
                uint64_t cur = carry;
                if (i < a.limb.size()) cur += a.limb[i];
                if (i < b.limb.size()) cur += b.limb[i];
                sum.limb[i] = static_cast<uint32_t>(cur);
                carry = cur >> 32;
            }
            sum.trim();
            // shift right by 1
            uint32_t c = 0;
            for (size_t i = sum.limb.size(); i-- > 0;) {
                uint32_t nc = sum.limb[i] & 1u;
                sum.limb[i] = (sum.limb[i] >> 1) | (c << 31);
                c = nc;
            }
            sum.trim();
        }
        BigNum mid = sum;
        if (BigNum::cmp(mid, lo) == 0) break; // converged: lo == mid

        // mid^root
        BigNum p = mid;
        for (unsigned r = 1; r < root; ++r) p = BigNum::mul(p, mid);

        if (BigNum::cmp(p, n) <= 0) lo = mid;
        else {
            // hi = mid - 1
            BigNum m = mid;
            size_t i = 0;
            while (i < m.limb.size()) {
                if (m.limb[i] != 0) { m.limb[i] -= 1; break; }
                m.limb[i] = 0xFFFFFFFFu;
                ++i;
            }
            m.trim();
            hi = m;
        }
        if (BigNum::cmp(lo, hi) >= 0) break;
    }
    return lo;
}

// First `bits` fractional bits of prime^(1/root):
//   frac_bits = floor(prime^(1/root) * 2^bits) mod 2^bits
//             = floor((prime << (root*bits))^(1/root)) mod 2^bits
inline uint64_t root_frac_bits(uint32_t prime, unsigned root, unsigned bits) {
    BigNum n = BigNum::shl(BigNum::from_u64(prime), root * bits);
    BigNum r = integer_nth_root(n, root);
    uint64_t v = r.low64();
    if (bits < 64) v &= (uint64_t(1) << bits) - 1;
    return v;
}

inline std::vector<uint32_t> first_primes(size_t count) {
    std::vector<uint32_t> primes;
    for (uint32_t c = 2; primes.size() < count; ++c) {
        bool is_p = true;
        for (uint32_t d = 2; d * d <= c; ++d) {
            if (c % d == 0) { is_p = false; break; }
        }
        if (is_p) primes.push_back(c);
    }
    return primes;
}

struct Sha256Tables {
    std::array<uint32_t, 8> H0;
    std::array<uint32_t, 64> K;
    Sha256Tables() {
        auto p = first_primes(64);
        for (int i = 0; i < 8; ++i)
            H0[static_cast<size_t>(i)] = static_cast<uint32_t>(root_frac_bits(p[static_cast<size_t>(i)], 2, 32));
        for (int i = 0; i < 64; ++i)
            K[static_cast<size_t>(i)] = static_cast<uint32_t>(root_frac_bits(p[static_cast<size_t>(i)], 3, 32));
    }
};

struct Sha512Tables {
    std::array<uint64_t, 8> H0;
    std::array<uint64_t, 80> K;
    Sha512Tables() {
        auto p = first_primes(80);
        for (int i = 0; i < 8; ++i)
            H0[static_cast<size_t>(i)] = root_frac_bits(p[static_cast<size_t>(i)], 2, 64);
        for (int i = 0; i < 80; ++i)
            K[static_cast<size_t>(i)] = root_frac_bits(p[static_cast<size_t>(i)], 3, 64);
    }
};

inline const Sha256Tables& sha256_tables() {
    static const Sha256Tables t; // magic static: thread-safe one-time derivation
    return t;
}
inline const Sha512Tables& sha512_tables() {
    static const Sha512Tables t;
    return t;
}

} // namespace sha2_detail

// ─────────────────────────────────────────────────────────────
// SHA-256
// ─────────────────────────────────────────────────────────────
class SHA256 {
private:
    uint32_t state_[8];
    uint64_t bitlen_ = 0;
    uint8_t buffer_[64];
    size_t buflen_ = 0;

    static uint32_t rotr(uint32_t x, unsigned n) { return (x >> n) | (x << (32 - n)); }

    void compress(const uint8_t block[64]) {
        const auto& T = sha2_detail::sha256_tables();
        uint32_t w[64];
        for (int i = 0; i < 16; ++i) {
            w[i] = (uint32_t(block[i * 4]) << 24) | (uint32_t(block[i * 4 + 1]) << 16) |
                   (uint32_t(block[i * 4 + 2]) << 8) | uint32_t(block[i * 4 + 3]);
        }
        for (int i = 16; i < 64; ++i) {
            uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        uint32_t a = state_[0], b = state_[1], c = state_[2], d = state_[3];
        uint32_t e = state_[4], f = state_[5], g = state_[6], h = state_[7];
        for (int i = 0; i < 64; ++i) {
            uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            uint32_t ch = (e & f) ^ (~e & g);
            uint32_t t1 = h + S1 + ch + T.K[static_cast<size_t>(i)] + w[i];
            uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
            uint32_t t2 = S0 + mj;
            h = g; g = f; f = e; e = d + t1;
            d = c; c = b; b = a; a = t1 + t2;
        }
        state_[0] += a; state_[1] += b; state_[2] += c; state_[3] += d;
        state_[4] += e; state_[5] += f; state_[6] += g; state_[7] += h;
    }

public:
    SHA256() { Init(); }

    void Init() {
        const auto& T = sha2_detail::sha256_tables();
        for (int i = 0; i < 8; ++i) state_[i] = T.H0[static_cast<size_t>(i)];
        bitlen_ = 0;
        buflen_ = 0;
    }

    void Update(const void* data, size_t len) {
        const uint8_t* p = static_cast<const uint8_t*>(data);
        bitlen_ += static_cast<uint64_t>(len) * 8;
        while (len > 0) {
            size_t take = std::min(len, sizeof(buffer_) - buflen_);
            std::memcpy(buffer_ + buflen_, p, take);
            buflen_ += take;
            p += take;
            len -= take;
            if (buflen_ == sizeof(buffer_)) {
                compress(buffer_);
                buflen_ = 0;
            }
        }
    }

    void Final(uint8_t out[32]) {
        uint64_t bl = bitlen_;
        uint8_t pad = 0x80;
        Update(&pad, 1);
        uint8_t zero = 0;
        while (buflen_ != 56) Update(&zero, 1);
        uint8_t lenb[8];
        for (int i = 0; i < 8; ++i) lenb[i] = static_cast<uint8_t>(bl >> (56 - 8 * i));
        // Feed length bytes directly (bypass bitlen accounting — already fixed)
        std::memcpy(buffer_ + buflen_, lenb, 8);
        compress(buffer_);
        buflen_ = 0;
        for (int i = 0; i < 8; ++i) {
            out[i * 4] = static_cast<uint8_t>(state_[i] >> 24);
            out[i * 4 + 1] = static_cast<uint8_t>(state_[i] >> 16);
            out[i * 4 + 2] = static_cast<uint8_t>(state_[i] >> 8);
            out[i * 4 + 3] = static_cast<uint8_t>(state_[i]);
        }
    }

    static std::array<uint8_t, 32> Hash(const void* data, size_t len) {
        SHA256 h;
        h.Update(data, len);
        std::array<uint8_t, 32> out{};
        h.Final(out.data());
        return out;
    }
};

// ─────────────────────────────────────────────────────────────
// SHA-512
// ─────────────────────────────────────────────────────────────
class SHA512 {
private:
    uint64_t state_[8];
    uint64_t bitlen_lo_ = 0; // messages < 2^64 bits (ample for our use)
    uint8_t buffer_[128];
    size_t buflen_ = 0;

    static uint64_t rotr(uint64_t x, unsigned n) { return (x >> n) | (x << (64 - n)); }

    void compress(const uint8_t block[128]) {
        const auto& T = sha2_detail::sha512_tables();
        uint64_t w[80];
        for (int i = 0; i < 16; ++i) {
            uint64_t v = 0;
            for (int b = 0; b < 8; ++b) v = (v << 8) | block[i * 8 + b];
            w[i] = v;
        }
        for (int i = 16; i < 80; ++i) {
            uint64_t s0 = rotr(w[i - 15], 1) ^ rotr(w[i - 15], 8) ^ (w[i - 15] >> 7);
            uint64_t s1 = rotr(w[i - 2], 19) ^ rotr(w[i - 2], 61) ^ (w[i - 2] >> 6);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        uint64_t a = state_[0], b = state_[1], c = state_[2], d = state_[3];
        uint64_t e = state_[4], f = state_[5], g = state_[6], h = state_[7];
        for (int i = 0; i < 80; ++i) {
            uint64_t S1 = rotr(e, 14) ^ rotr(e, 18) ^ rotr(e, 41);
            uint64_t ch = (e & f) ^ (~e & g);
            uint64_t t1 = h + S1 + ch + T.K[static_cast<size_t>(i)] + w[i];
            uint64_t S0 = rotr(a, 28) ^ rotr(a, 34) ^ rotr(a, 39);
            uint64_t mj = (a & b) ^ (a & c) ^ (b & c);
            uint64_t t2 = S0 + mj;
            h = g; g = f; f = e; e = d + t1;
            d = c; c = b; b = a; a = t1 + t2;
        }
        state_[0] += a; state_[1] += b; state_[2] += c; state_[3] += d;
        state_[4] += e; state_[5] += f; state_[6] += g; state_[7] += h;
    }

public:
    SHA512() { Init(); }

    void Init() {
        const auto& T = sha2_detail::sha512_tables();
        for (int i = 0; i < 8; ++i) state_[i] = T.H0[static_cast<size_t>(i)];
        bitlen_lo_ = 0;
        buflen_ = 0;
    }

    void Update(const void* data, size_t len) {
        const uint8_t* p = static_cast<const uint8_t*>(data);
        bitlen_lo_ += static_cast<uint64_t>(len) * 8;
        while (len > 0) {
            size_t take = std::min(len, sizeof(buffer_) - buflen_);
            std::memcpy(buffer_ + buflen_, p, take);
            buflen_ += take;
            p += take;
            len -= take;
            if (buflen_ == sizeof(buffer_)) {
                compress(buffer_);
                buflen_ = 0;
            }
        }
    }

    void Final(uint8_t out[64]) {
        uint64_t bl = bitlen_lo_;
        uint8_t pad = 0x80;
        Update(&pad, 1);
        uint8_t zero = 0;
        while (buflen_ != 112) Update(&zero, 1);
        // 128-bit big-endian length; high 64 bits are zero for our sizes
        uint8_t lenb[16] = {0};
        for (int i = 0; i < 8; ++i) lenb[8 + i] = static_cast<uint8_t>(bl >> (56 - 8 * i));
        std::memcpy(buffer_ + buflen_, lenb, 16);
        compress(buffer_);
        buflen_ = 0;
        for (int i = 0; i < 8; ++i) {
            for (int b = 0; b < 8; ++b) {
                out[i * 8 + b] = static_cast<uint8_t>(state_[i] >> (56 - 8 * b));
            }
        }
    }

    static std::array<uint8_t, 64> Hash(const void* data, size_t len) {
        SHA512 h;
        h.Update(data, len);
        std::array<uint8_t, 64> out{};
        h.Final(out.data());
        return out;
    }
};

// Hex helpers used across the update pipeline.
inline std::string ToHex(const uint8_t* data, size_t len) {
    static const char* digits = "0123456789abcdef";
    std::string out;
    out.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) {
        out += digits[data[i] >> 4];
        out += digits[data[i] & 0xF];
    }
    return out;
}

inline bool FromHex(const std::string& hex, uint8_t* out, size_t out_len) {
    if (hex.size() != out_len * 2) return false;
    auto nib = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    for (size_t i = 0; i < out_len; ++i) {
        int hi = nib(hex[i * 2]);
        int lo = nib(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = static_cast<uint8_t>((hi << 4) | lo);
    }
    return true;
}

// Constant-time comparison — no early exit on first mismatching byte.
inline bool ConstantTimeEqual(const uint8_t* a, const uint8_t* b, size_t len) {
    uint8_t diff = 0;
    for (size_t i = 0; i < len; ++i) diff |= static_cast<uint8_t>(a[i] ^ b[i]);
    return diff == 0;
}

} // namespace neuroshell::crypto
