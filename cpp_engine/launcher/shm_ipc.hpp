// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// SHMRingBuffer — cross-language shared-memory ring for C++ host <-> Python daemon.
//
// v5.8 ABI fix: the previous header relied on `#pragma pack(1)` + `alignas(64)`
// which compiled to cursors at offsets 16/24 (sizeof == 64) while the Python
// bridge (core/shm_bridge.py) reads cursors at offsets 64/72 and payload at 128.
// The two sides could NEVER interoperate. The layout below is now explicit and
// byte-for-byte identical to the Python side.
//
// v5.10 ABI v3 — token streaming (Phase 2 of the engineering roadmap):
//   * Rings are now NAMED — the host owns TWO independent unidirectional
//     rings: the event ring (host → daemon, unchanged role) and a new
//     STREAM ring (daemon → host) that carries AI tokens with sub-frame
//     latency instead of waiting for the full socket response.
//   * New header field `cancel_stream_id` (offset 84): the CONSUMER (host)
//     stores a stream id there to request cooperative cancellation; the
//     PRODUCER (daemon) checks it between tokens and aborts generation.
//   * Stream frames are binary: [u8 type][u32 stream_id LE][utf-8 text],
//     carried as ordinary length-prefixed ring messages. Type is TOKEN,
//     END or ERROR; frames from stale stream ids are discarded by readers.
//
//   offset   0  u32  magic            "NEUR" (0x4E455552)
//   offset   4  u32  version          == 3
//   offset   8  u32  capacity
//   offset  12  u32  flags
//   offset  64  u64  write_cursor     (atomic, release/acquire)
//   offset  72  u64  read_cursor      (atomic, release/acquire)
//   offset  80  u32  message_seq      (atomic)
//   offset  84  u32  cancel_stream_id (atomic; consumer → producer)
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
constexpr uint32_t SHM_ABI_VERSION = 3;
constexpr uint32_t SHM_HEADER_SIZE = 128;               // data starts here

// Named rings. The legacy names stay bound to the event ring so any v2-era
// tooling fails ABI validation (version 3) rather than silently desyncing.
constexpr const char* SHM_WIN_NAME = "Local\\NeuroShell_SHM_Ring";
constexpr const char* SHM_POSIX_NAME = "/neuroshell_shm_ring";
constexpr const char* SHM_STREAM_WIN_NAME = "Local\\NeuroShell_SHM_Stream";
constexpr const char* SHM_STREAM_POSIX_NAME = "/neuroshell_shm_stream";

// Stream-frame types carried on the stream ring (daemon → host).
enum class StreamFrameType : uint8_t {
    Token = 1, // incremental UTF-8 text
    End   = 2, // stream complete (payload may carry stats JSON)
    Error = 3, // stream aborted (payload carries the error message)
};

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
    std::atomic<uint32_t> cancel_stream_id;     // 84 (consumer → producer)
    uint8_t  _pad1[40];                         // 88..127
};

static_assert(offsetof(SHMHeader, write_cursor) == 64, "SHM ABI: write_cursor must be at offset 64");
static_assert(offsetof(SHMHeader, read_cursor) == 72, "SHM ABI: read_cursor must be at offset 72");
static_assert(offsetof(SHMHeader, message_sequence) == 80, "SHM ABI: message_sequence must be at offset 80");
static_assert(offsetof(SHMHeader, cancel_stream_id) == 84, "SHM ABI: cancel_stream_id must be at offset 84");
static_assert(sizeof(SHMHeader) == SHM_HEADER_SIZE, "SHM ABI: header must be exactly 128 bytes");
static_assert(std::atomic<uint64_t>::is_always_lock_free, "SHM requires lock-free 64-bit atomics");

class SHMRingBuffer {
private:
    SHMHeader* header_{nullptr};
    uint8_t* ring_data_{nullptr};
    bool is_owner_{false};
    bool is_connected_{false};
    std::string win_name_{SHM_WIN_NAME};
    std::string posix_name_{SHM_POSIX_NAME};

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
                                        0, static_cast<DWORD>(TotalSize()), win_name_.c_str());
        } else {
            h_map_ = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, win_name_.c_str());
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
        shm_fd_ = shm_open(posix_name_.c_str(), flags, 0600);
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

    // Named-ring constructor: bind this instance to a specific ring (event
    // ring by default; pass SHM_STREAM_* names for the token-stream ring).
    SHMRingBuffer(std::string win_name, std::string posix_name)
        : win_name_(std::move(win_name)), posix_name_(std::move(posix_name)) {}

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
        header_->cancel_stream_id.store(0, std::memory_order_relaxed);

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

    // ═══════════ ABI v3: token-stream frames (Phase 2) ═══════════
    // Frame layout inside an ordinary length-prefixed ring message:
    //   [u8 type][u32 stream_id LE][utf-8 payload]
    // Mirrored byte-for-byte by core/shm_bridge.py.

    struct StreamFrame {
        StreamFrameType type = StreamFrameType::Error;
        uint32_t stream_id = 0;
        std::string payload;
    };

    bool write_frame(StreamFrameType type, uint32_t stream_id, std::string_view payload) {
        std::string msg;
        msg.reserve(5 + payload.size());
        msg.push_back(static_cast<char>(type));
        char id_le[4];
        std::memcpy(id_le, &stream_id, 4); // little-endian on all supported targets
        msg.append(id_le, 4);
        msg.append(payload.data(), payload.size());
        return write_message(msg);
    }

    // Reads the next frame. Returns false when the ring is empty or the
    // message is too short to be a frame (desync-corrupt frames are dropped,
    // never surfaced as tokens).
    bool read_frame(StreamFrame& out) {
        std::string raw;
        if (!read_message(raw)) return false;
        if (raw.size() < 5) return false;
        uint8_t t = static_cast<uint8_t>(raw[0]);
        if (t < static_cast<uint8_t>(StreamFrameType::Token) ||
            t > static_cast<uint8_t>(StreamFrameType::Error)) {
            return false;
        }
        out.type = static_cast<StreamFrameType>(t);
        std::memcpy(&out.stream_id, raw.data() + 1, 4);
        out.payload.assign(raw, 5, raw.size() - 5);
        return true;
    }

    // Cooperative cancellation: the consumer publishes the stream id it wants
    // aborted; the producer polls this between tokens.
    void request_cancel(uint32_t stream_id) {
        if (header_) header_->cancel_stream_id.store(stream_id, std::memory_order_release);
    }

    uint32_t cancel_requested() const {
        return header_ ? header_->cancel_stream_id.load(std::memory_order_acquire) : 0;
    }

    void clear_cancel() {
        if (header_) header_->cancel_stream_id.store(0, std::memory_order_release);
    }

    // Drop any unread bytes (used when a stream is cancelled so stale tokens
    // from the aborted stream don't leak into the next one).
    void drain() {
        if (!header_) return;
        uint64_t w = header_->write_cursor.load(std::memory_order_acquire);
        header_->read_cursor.store(w, std::memory_order_release);
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
                shm_unlink(posix_name_.c_str());
            }
#endif
            header_ = nullptr;
            ring_data_ = nullptr;
        }
        is_connected_ = false;
    }
};

} // namespace neuroshell
