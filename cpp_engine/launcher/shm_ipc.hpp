// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// SHMRingBuffer — cross-language shared-memory ring for C++ host <-> Python daemon.
//
// v5.8 ABI fix: the previous header relied on `#pragma pack(1)` + `alignas(64)`
// which compiled to cursors at offsets 16/24 (sizeof == 64) while the Python
// bridge (core/shm_bridge.py) reads cursors at offsets 64/72 and payload at 128.
// The two sides could NEVER interoperate. The layout below is now explicit and
// byte-for-byte identical to the Python side:
//
//   offset   0  u32  magic        "NEUR" (0x4E455552)
//   offset   4  u32  version      == 2
//   offset   8  u32  capacity
//   offset  12  u32  flags
//   offset  64  u64  write_cursor (atomic, release/acquire)
//   offset  72  u64  read_cursor  (atomic, release/acquire)
//   offset  80  u32  message_seq  (atomic)
//   offset 128  u8[] ring data (SHM_RING_CAPACITY bytes)
#pragma once

#include <atomic>
#include <cstdint>
#include <cstring>
#include <string>
#include <string_view>

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#endif

namespace neuroshell {

constexpr uint32_t SHM_RING_CAPACITY = 8 * 1024 * 1024; // 8 MB ring
constexpr uint32_t SHM_MAGIC = 0x4E455552;              // "NEUR"
constexpr uint32_t SHM_ABI_VERSION = 2;
constexpr uint32_t SHM_HEADER_SIZE = 128;               // data starts here
constexpr const char* SHM_WIN_NAME = "Local\\NeuroShell_SHM_Ring";
constexpr const char* SHM_POSIX_NAME = "/neuroshell_shm_ring";

// Explicit fixed layout — no packing tricks, offsets asserted at compile time.
struct SHMHeader {
    uint32_t magic;                             // 0
    uint32_t version;                           // 4
    uint32_t capacity;                          // 8
    uint32_t flags;                             // 12
    uint8_t  _pad0[48];                         // 16..63
    std::atomic<uint64_t> write_cursor;         // 64
    std::atomic<uint64_t> read_cursor;          // 72
    std::atomic<uint32_t> message_sequence;     // 80
    uint8_t  _pad1[44];                         // 84..127
};

static_assert(offsetof(SHMHeader, write_cursor) == 64, "SHM ABI: write_cursor must be at offset 64");
static_assert(offsetof(SHMHeader, read_cursor) == 72, "SHM ABI: read_cursor must be at offset 72");
static_assert(offsetof(SHMHeader, message_sequence) == 80, "SHM ABI: message_sequence must be at offset 80");
static_assert(sizeof(SHMHeader) == SHM_HEADER_SIZE, "SHM ABI: header must be exactly 128 bytes");
static_assert(std::atomic<uint64_t>::is_always_lock_free, "SHM requires lock-free 64-bit atomics");

class SHMRingBuffer {
private:
    SHMHeader* header_{nullptr};
    uint8_t* ring_data_{nullptr};
    bool is_owner_{false};
    bool is_connected_{false};

#if defined(_WIN32)
    HANDLE h_map_{nullptr};
#else
    int shm_fd_{-1};
#endif

    static constexpr size_t TotalSize() {
        return SHM_HEADER_SIZE + SHM_RING_CAPACITY;
    }

    bool map_memory(bool create) {
#if defined(_WIN32)
        if (create) {
            h_map_ = CreateFileMappingA(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE,
                                        0, static_cast<DWORD>(TotalSize()), SHM_WIN_NAME);
        } else {
            h_map_ = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, SHM_WIN_NAME);
        }
        if (!h_map_) return false;

        void* ptr = MapViewOfFile(h_map_, FILE_MAP_ALL_ACCESS, 0, 0, TotalSize());
        if (!ptr) {
            CloseHandle(h_map_);
            h_map_ = nullptr;
            return false;
        }
#else
        int flags = create ? (O_CREAT | O_RDWR) : O_RDWR;
        shm_fd_ = shm_open(SHM_POSIX_NAME, flags, 0600);
        if (shm_fd_ < 0) return false;
        if (create && ftruncate(shm_fd_, static_cast<off_t>(TotalSize())) != 0) {
            ::close(shm_fd_);
            shm_fd_ = -1;
            return false;
        }

        void* ptr = mmap(nullptr, TotalSize(), PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd_, 0);
        if (ptr == MAP_FAILED) {
            ::close(shm_fd_);
            shm_fd_ = -1;
            return false;
        }
#endif
        header_ = reinterpret_cast<SHMHeader*>(ptr);
        ring_data_ = reinterpret_cast<uint8_t*>(ptr) + SHM_HEADER_SIZE;
        return true;
    }

    // Copy `len` bytes into the ring starting at logical position `pos`
    // using at most two memcpy segments (wrap-aware).
    void ring_write(uint64_t pos, const uint8_t* src, uint32_t len) {
        uint32_t start = static_cast<uint32_t>(pos % SHM_RING_CAPACITY);
        uint32_t first = (start + len <= SHM_RING_CAPACITY) ? len : (SHM_RING_CAPACITY - start);
        std::memcpy(ring_data_ + start, src, first);
        if (first < len) {
            std::memcpy(ring_data_, src + first, len - first);
        }
    }

    void ring_read(uint64_t pos, uint8_t* dst, uint32_t len) const {
        uint32_t start = static_cast<uint32_t>(pos % SHM_RING_CAPACITY);
        uint32_t first = (start + len <= SHM_RING_CAPACITY) ? len : (SHM_RING_CAPACITY - start);
        std::memcpy(dst, ring_data_ + start, first);
        if (first < len) {
            std::memcpy(dst + first, ring_data_, len - first);
        }
    }

public:
    SHMRingBuffer() = default;

    ~SHMRingBuffer() {
        close();
    }

    SHMRingBuffer(const SHMRingBuffer&) = delete;
    SHMRingBuffer& operator=(const SHMRingBuffer&) = delete;

    bool initialize_as_host() {
        close();
        is_owner_ = true;
        if (!map_memory(/*create=*/true)) return false;

        header_->magic = SHM_MAGIC;
        header_->version = SHM_ABI_VERSION;
        header_->capacity = SHM_RING_CAPACITY;
        header_->flags = 0;
        header_->write_cursor.store(0, std::memory_order_relaxed);
        header_->read_cursor.store(0, std::memory_order_relaxed);
        header_->message_sequence.store(0, std::memory_order_relaxed);

        is_connected_ = true;
        return true;
    }

    // Attach to an existing ring (peer side) and validate the ABI header.
    bool attach_as_client() {
        close();
        is_owner_ = false;
        if (!map_memory(/*create=*/false)) return false;

        if (header_->magic != SHM_MAGIC || header_->version != SHM_ABI_VERSION ||
            header_->capacity != SHM_RING_CAPACITY) {
            close();
            return false;
        }
        is_connected_ = true;
        return true;
    }

    bool is_connected() const { return is_connected_; }

    bool write_message(std::string_view payload) {
        if (!is_connected_ || !header_) return false;

        uint32_t len = static_cast<uint32_t>(payload.size());
        if (len + 4 > SHM_RING_CAPACITY / 2) return false; // Packet too large

        uint64_t w = header_->write_cursor.load(std::memory_order_relaxed);
        uint64_t r = header_->read_cursor.load(std::memory_order_acquire);

        if ((w - r) + len + 4 > SHM_RING_CAPACITY) {
            return false; // Ring full → backpressure
        }

        uint8_t len_le[4];
        std::memcpy(len_le, &len, 4); // little-endian on all supported targets
        ring_write(w, len_le, 4);
        ring_write(w + 4, reinterpret_cast<const uint8_t*>(payload.data()), len);

        header_->write_cursor.store(w + 4 + len, std::memory_order_release);
        header_->message_sequence.fetch_add(1, std::memory_order_relaxed);
        return true;
    }

    bool read_message(std::string& out_payload) {
        if (!is_connected_ || !header_) return false;

        uint64_t r = header_->read_cursor.load(std::memory_order_relaxed);
        uint64_t w = header_->write_cursor.load(std::memory_order_acquire);

        if (r >= w) return false; // Empty

        uint8_t len_le[4];
        ring_read(r, len_le, 4);
        uint32_t len = 0;
        std::memcpy(&len, len_le, 4);

        if (len > SHM_RING_CAPACITY / 2 || r + 4 + len > w) {
            // Corrupt / desynced — fast-forward to writer position.
            header_->read_cursor.store(w, std::memory_order_release);
            return false;
        }

        out_payload.resize(len);
        ring_read(r + 4, reinterpret_cast<uint8_t*>(out_payload.data()), len);

        header_->read_cursor.store(r + 4 + len, std::memory_order_release);
        return true;
    }

    void close() {
        if (header_) {
#if defined(_WIN32)
            UnmapViewOfFile(header_);
            if (h_map_) {
                CloseHandle(h_map_);
                h_map_ = nullptr;
            }
#else
            munmap(header_, TotalSize());
            if (shm_fd_ >= 0) {
                ::close(shm_fd_);
                shm_fd_ = -1;
            }
            if (is_owner_) {
                shm_unlink(SHM_POSIX_NAME);
            }
#endif
            header_ = nullptr;
            ring_data_ = nullptr;
        }
        is_connected_ = false;
    }
};

} // namespace neuroshell
