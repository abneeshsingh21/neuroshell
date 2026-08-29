// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// Ed25519 — VERIFY-ONLY implementation for the update pipeline.
//
// Provenance & design notes (v5.9 update-security work):
//   * The field/point arithmetic is a careful C++ port of the public-domain
//     TweetNaCl construction (Bernstein, van Gastel, Janssen, Lange,
//     Schwabe, Wilcox-O'Hearn) — chosen because it is the most-audited
//     compact Ed25519 codebase in existence and its arithmetic is branch-
//     free on secret-independent data. Only the verification path is
//     ported: this binary can never sign, so no private-key material or
//     signing arithmetic exists in the process image.
//   * All curve constants (d, 2d, sqrt(-1), base point) are DERIVED at
//     startup from their mathematical definitions using the ported field
//     arithmetic itself — none are hand-typed tables. The group order L is
//     the single hardcoded constant (documented below) and any corruption
//     of it is caught by the cross-implementation test vectors.
//   * Beyond TweetNaCl we additionally enforce the RFC 8032 malleability
//     rule: signatures with S >= L are rejected outright, so each message
//     has exactly one accepted signature encoding.
//   * Correctness is proven against vectors generated with Python
//     `cryptography` (OpenSSL-backed) in cpp_engine/tests.
#pragma once

#include "sha2.hpp"

#include <cstdint>
#include <cstring>

namespace neuroshell::crypto {

namespace ed25519_detail {

using i64 = int64_t;
using u8 = uint8_t;
typedef i64 gf[16]; // radix-2^16 little-endian field element mod 2^255-19

inline void set25519(gf r, const gf a) {
    for (int i = 0; i < 16; ++i) r[i] = a[i];
}

inline void car25519(gf o) {
    for (int i = 0; i < 16; ++i) {
        o[i] += (i64(1) << 16);
        i64 c = o[i] >> 16;
        o[(i + 1) * (i < 15)] += c - 1 + 37 * (c - 1) * (i == 15);
        o[i] -= c << 16;
    }
}

// Constant-time conditional swap: b must be 0 or 1.
inline void sel25519(gf p, gf q, int b) {
    i64 c = ~static_cast<i64>(b - 1);
    for (int i = 0; i < 16; ++i) {
        i64 t = c & (p[i] ^ q[i]);
        p[i] ^= t;
        q[i] ^= t;
    }
}

inline void pack25519(u8* o, const gf n) {
    gf m, t;
    for (int i = 0; i < 16; ++i) t[i] = n[i];
    car25519(t);
    car25519(t);
    car25519(t);
    for (int j = 0; j < 2; ++j) {
        m[0] = t[0] - 0xffed;
        for (int i = 1; i < 15; ++i) {
            m[i] = t[i] - 0xffff - ((m[i - 1] >> 16) & 1);
            m[i - 1] &= 0xffff;
        }
        m[15] = t[15] - 0x7fff - ((m[14] >> 16) & 1);
        int b = (m[15] >> 16) & 1;
        m[14] &= 0xffff;
        sel25519(t, m, 1 - b);
    }
    for (int i = 0; i < 16; ++i) {
        o[2 * i] = static_cast<u8>(t[i] & 0xff);
        o[2 * i + 1] = static_cast<u8>(t[i] >> 8);
    }
}

inline u8 par25519(const gf a) {
    u8 d[32];
    pack25519(d, a);
    return d[0] & 1;
}

inline void unpack25519(gf o, const u8* n) {
    for (int i = 0; i < 16; ++i) o[i] = n[2 * i] + (static_cast<i64>(n[2 * i + 1]) << 8);
    o[15] &= 0x7fff;
}

inline void fadd(gf o, const gf a, const gf b) { // A
    for (int i = 0; i < 16; ++i) o[i] = a[i] + b[i];
}

inline void fsub(gf o, const gf a, const gf b) { // Z
    for (int i = 0; i < 16; ++i) o[i] = a[i] - b[i];
}

inline void fmul(gf o, const gf a, const gf b) { // M
    i64 t[31];
    for (int i = 0; i < 31; ++i) t[i] = 0;
    for (int i = 0; i < 16; ++i)
        for (int j = 0; j < 16; ++j) t[i + j] += a[i] * b[j];
    for (int i = 0; i < 15; ++i) t[i] += 38 * t[i + 16];
    for (int i = 0; i < 16; ++i) o[i] = t[i];
    car25519(o);
    car25519(o);
}

inline void fsquare(gf o, const gf a) { fmul(o, a, a); } // S

inline void inv25519(gf o, const gf i) { // x^(p-2) = x^-1
    gf c;
    for (int a = 0; a < 16; ++a) c[a] = i[a];
    for (int a = 253; a >= 0; --a) {
        fsquare(c, c);
        if (a != 2 && a != 4) fmul(c, c, i);
    }
    for (int a = 0; a < 16; ++a) o[a] = c[a];
}

inline void pow2523(gf o, const gf i) { // x^((p-5)/8)
    gf c;
    for (int a = 0; a < 16; ++a) c[a] = i[a];
    for (int a = 250; a >= 0; --a) {
        fsquare(c, c);
        if (a != 1) fmul(c, c, i);
    }
    for (int a = 0; a < 16; ++a) o[a] = c[a];
}

inline int neq25519(const gf a, const gf b) {
    u8 c[32], d[32];
    pack25519(c, a);
    pack25519(d, b);
    return ConstantTimeEqual(c, d, 32) ? 0 : 1;
}

inline void set_small(gf r, i64 v) {
    for (int i = 0; i < 16; ++i) r[i] = 0;
    r[0] = v & 0xffff;
    r[1] = (v >> 16) & 0xffff;
    r[2] = (v >> 32) & 0xffff;
}

// ─── Curve constants: DERIVED, not typed ─────────────────────
// d      = -121665/121666 mod p          (Edwards curve constant)
// sqrtm1 = 2^((p-1)/4) mod p             (a square root of -1)
// By     = 4/5 mod p                     (base point y)
// Bx     = decompress(By, sign=0)        (base point x, even)
struct CurveConsts {
    gf gf0, gf1, D, D2, sqrtm1, Bx, By;

    CurveConsts() {
        set_small(gf0, 0);
        set_small(gf1, 1);

        // D = -121665 * inv(121666)
        gf a, b, binv;
        set_small(a, 121665);
        set_small(b, 121666);
        inv25519(binv, b);
        fmul(D, a, binv);
        fsub(D, gf0, D);
        car25519(D);
        car25519(D);

        // D2 = 2*D
        fadd(D2, D, D);
        car25519(D2);
        car25519(D2);

        // sqrtm1 = 2^((p-1)/4) = 2^(2^253) * inv(2^5)
        gf two, acc, thirty_two, inv32;
        set_small(two, 2);
        set25519(acc, two);
        for (int i = 0; i < 253; ++i) fsquare(acc, acc);
        set_small(thirty_two, 32);
        inv25519(inv32, thirty_two);
        fmul(sqrtm1, acc, inv32);

        // By = 4 * inv(5)
        gf four, five, inv5;
        set_small(four, 4);
        set_small(five, 5);
        inv25519(inv5, five);
        fmul(By, four, inv5);

        // Bx = sqrt((By^2 - 1) / (d*By^2 + 1)) with even parity.
        gf num, den, den2, den4, den6, t, chk;
        fsquare(num, By);
        fmul(den, num, D);
        fsub(num, num, gf1);
        fadd(den, gf1, den);
        fsquare(den2, den);
        fsquare(den4, den2);
        fmul(den6, den4, den2);
        fmul(t, den6, num);
        fmul(t, t, den);
        pow2523(t, t);
        fmul(t, t, num);
        fmul(t, t, den);
        fmul(t, t, den);
        fmul(Bx, t, den);
        fsquare(chk, Bx);
        fmul(chk, chk, den);
        if (neq25519(chk, num)) fmul(Bx, Bx, sqrtm1);
        if (par25519(Bx) != 0) { // canonical basepoint x is even
            fsub(Bx, gf0, Bx);
            car25519(Bx);
            car25519(Bx);
        }
    }
};

inline const CurveConsts& consts() {
    static const CurveConsts c; // thread-safe one-time derivation
    return c;
}

// ─── Edwards point arithmetic (extended coordinates) ─────────
inline void point_add(gf p[4], gf q[4]) {
    const CurveConsts& C = consts();
    gf a, b, c, d, t, e, f, g, h;
    fsub(a, p[1], p[0]);
    fsub(t, q[1], q[0]);
    fmul(a, a, t);
    fadd(b, p[0], p[1]);
    fadd(t, q[0], q[1]);
    fmul(b, b, t);
    fmul(c, p[3], q[3]);
    fmul(c, c, C.D2);
    fmul(d, p[2], q[2]);
    fadd(d, d, d);
    fsub(e, b, a);
    fsub(f, d, c);
    fadd(g, d, c);
    fadd(h, b, a);
    fmul(p[0], e, f);
    fmul(p[1], h, g);
    fmul(p[2], g, f);
    fmul(p[3], e, h);
}

inline void point_cswap(gf p[4], gf q[4], u8 b) {
    for (int i = 0; i < 4; ++i) sel25519(p[i], q[i], b);
}

inline void point_pack(u8* r, gf p[4]) {
    gf tx, ty, zi;
    inv25519(zi, p[2]);
    fmul(tx, p[0], zi);
    fmul(ty, p[1], zi);
    pack25519(r, ty);
    r[31] ^= static_cast<u8>(par25519(tx) << 7);
}

inline void point_scalarmult(gf p[4], gf q[4], const u8* s) {
    const CurveConsts& C = consts();
    set25519(p[0], C.gf0);
    set25519(p[1], C.gf1);
    set25519(p[2], C.gf1);
    set25519(p[3], C.gf0);
    for (int i = 255; i >= 0; --i) {
        u8 b = (s[i / 8] >> (i & 7)) & 1;
        point_cswap(p, q, b);
        point_add(q, p);
        point_add(p, p);
        point_cswap(p, q, b);
    }
}

inline void point_scalarbase(gf p[4], const u8* s) {
    const CurveConsts& C = consts();
    gf q[4];
    set25519(q[0], C.Bx);
    set25519(q[1], C.By);
    set25519(q[2], C.gf1);
    fmul(q[3], C.Bx, C.By);
    point_scalarmult(p, q, s);
}

// Decompress a public key into the NEGATED point (-A), as the verification
// equation computes R' = sB - hA. Returns false for invalid encodings
// (x-coordinate not on the curve).
inline bool unpack_neg(gf r[4], const u8 p[32]) {
    const CurveConsts& C = consts();
    gf t, chk, num, den, den2, den4, den6;
    set25519(r[2], C.gf1);
    unpack25519(r[1], p);
    fsquare(num, r[1]);
    fmul(den, num, C.D);
    fsub(num, num, r[2]);
    fadd(den, r[2], den);

    fsquare(den2, den);
    fsquare(den4, den2);
    fmul(den6, den4, den2);
    fmul(t, den6, num);
    fmul(t, t, den);

    pow2523(t, t);
    fmul(t, t, num);
    fmul(t, t, den);
    fmul(t, t, den);
    fmul(r[0], t, den);

    fsquare(chk, r[0]);
    fmul(chk, chk, den);
    if (neq25519(chk, num)) fmul(r[0], r[0], C.sqrtm1);

    fsquare(chk, r[0]);
    fmul(chk, chk, den);
    if (neq25519(chk, num)) return false;

    if (par25519(r[0]) == (p[31] >> 7)) {
        fsub(r[0], C.gf0, r[0]);
        car25519(r[0]);
        car25519(r[0]);
    }

    fmul(r[3], r[0], r[1]);
    return true;
}

// ─── Scalar arithmetic mod the group order L ─────────────────
// L = 2^252 + 27742317777372353535851937790883648493
//   = 0x1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3ed
// This is the only hardcoded constant in this file; the test-vector suite
// (signatures cross-generated with an independent implementation) fails
// closed if any byte of it is wrong.
inline const i64* order_L() {
    static const i64 L[32] = {
        0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58,
        0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14,
        0,    0,    0,    0,    0,    0,    0,    0,
        0,    0,    0,    0,    0,    0,    0,    0x10};
    return L;
}

inline void modL(u8* r, i64 x[64]) {
    const i64* L = order_L();
    i64 carry;
    for (int i = 63; i >= 32; --i) {
        carry = 0;
        int j;
        for (j = i - 32; j < i - 12; ++j) {
            x[j] += carry - 16 * x[i] * L[j - (i - 32)];
            carry = (x[j] + 128) >> 8;
            x[j] -= carry << 8;
        }
        x[j] += carry;
        x[i] = 0;
    }
    carry = 0;
    for (int j = 0; j < 32; ++j) {
        x[j] += carry - (x[31] >> 4) * L[j];
        carry = x[j] >> 8;
        x[j] &= 255;
    }
    for (int j = 0; j < 32; ++j) x[j] -= carry * L[j];
    for (int i = 0; i < 32; ++i) {
        x[i + 1] += x[i] >> 8;
        r[i] = static_cast<u8>(x[i] & 255);
    }
}

inline void reduce64(u8* r) { // r: 64 bytes in, 32-byte scalar mod L out
    i64 x[64];
    for (int i = 0; i < 64; ++i) x[i] = static_cast<i64>(r[i]);
    for (int i = 0; i < 64; ++i) r[i] = 0;
    modL(r, x);
}

// RFC 8032 §5.1.7 malleability check: reject S >= L so every message has a
// single accepted signature encoding. (TweetNaCl itself omits this.)
inline bool scalar_below_L(const u8 s[32]) {
    const i64* L = order_L();
    for (int i = 31; i >= 0; --i) {
        i64 sv = static_cast<i64>(s[i]);
        if (sv < L[i]) return true;
        if (sv > L[i]) return false;
    }
    return false; // s == L
}

} // namespace ed25519_detail

// ─────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────
class Ed25519 {
public:
    static constexpr size_t kPublicKeySize = 32;
    static constexpr size_t kSignatureSize = 64;

    // Verify a detached Ed25519 signature over `msg`.
    // Returns true ONLY when:
    //   * the public key decodes to a valid curve point,
    //   * S is canonical (S < L — malleable encodings rejected),
    //   * the group equation [S]B = R + [H(R,A,M)]A holds.
    static bool Verify(const uint8_t sig[64], const uint8_t* msg, size_t msg_len,
                       const uint8_t pk[32]) {
        using namespace ed25519_detail;

        if (sig == nullptr || pk == nullptr || (msg == nullptr && msg_len != 0)) return false;

        // 1. Malleability: S must be a canonical scalar.
        if (!scalar_below_L(sig + 32)) return false;

        // 2. Decode the public key (as -A).
        gf q[4];
        if (!unpack_neg(q, pk)) return false;

        // 3. h = SHA-512(R || A || M) mod L, streamed (no message copy).
        uint8_t h[64];
        {
            SHA512 hash;
            hash.Update(sig, 32);      // R
            hash.Update(pk, 32);       // A
            hash.Update(msg, msg_len); // M
            hash.Final(h);
        }
        reduce64(h);

        // 4. R' = [S]B + [h](-A)  ==  [S]B - [h]A
        gf p[4], sB[4];
        point_scalarmult(p, q, h);
        point_scalarbase(sB, sig + 32);
        point_add(p, sB);

        uint8_t t[32];
        point_pack(t, p);

        // 5. Constant-time equality with the encoded R from the signature.
        return ConstantTimeEqual(sig, t, 32);
    }

    // Convenience overload for hex-encoded inputs (as carried in manifests).
    static bool VerifyHex(const std::string& sig_hex, const uint8_t* msg, size_t msg_len,
                          const std::string& pk_hex) {
        uint8_t sig[kSignatureSize];
        uint8_t pk[kPublicKeySize];
        if (!FromHex(sig_hex, sig, sizeof(sig))) return false;
        if (!FromHex(pk_hex, pk, sizeof(pk))) return false;
        return Verify(sig, msg, msg_len, pk);
    }
};

} // namespace neuroshell::crypto
