// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
#pragma once

#include <atomic>
#include <cstdint>
#include <cstring>
#include <string>
#include <string_view>
#include <iostream>

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

constexpr uint32_t SHM_RING_CAPACITY = 8 * 1024 * 1024; // 8 MB Ring Buffer
constexpr uint32_t SHM_MAGIC = 0x4E455552; // "NEUR"
constexpr const char* SHM_WIN_NAME = "Local\\NeuroShell_SHM_Ring";
constexpr const char* SHM_POSIX_NAME = "/neuroshell_shm_ring";

#pragma pack(push, 1)
struct alignas(64) SHMHeader {
    uint32_t magic;
    uint32_t version;
    uint32_t capacity;
    uint32_t flags;
    alignas(64) std::atomic<uint64_t> write_cursor;
    alignas(64) std::atomic<uint64_t> read_cursor;
    alignas(64) std::atomic<uint32_t> message_sequence;
};
#pragma pack(pop)

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

public:
    SHMRingBuffer() = default;

    ~SHMRingBuffer() {
        close();
    }

    bool initialize_as_host() {
        close();
        is_owner_ = true;
        size_t total_size = sizeof(SHMHeader) + SHM_RING_CAPACITY;

#if defined(_WIN32)
        h_map_ = CreateFileMappingA(
            INVALID_HANDLE_VALUE,
            nullptr,
            PAGE_READWRITE,
            0,
            static_cast<DWORD>(total_size),
            SHM_WIN_NAME
        );

        if (!h_map_) return false;

        void* ptr = MapViewOfFile(h_map_, FILE_MAP_ALL_ACCESS, 0, 0, total_size);
        if (!ptr) {
            CloseHandle(h_map_);
            h_map_ = nullptr;
            return false;
        }
#else
        shm_fd_ = shm_open(SHM_POSIX_NAME, O_CREAT | O_RDWR, 0600);
        if (shm_fd_ < 0) return false;
        if (ftruncate(shm_fd_, total_size) != 0) {
            ::close(shm_fd_);
            shm_fd_ = -1;
            return false;
        }

        void* ptr = mmap(nullptr, total_size, PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd_, 0);
        if (ptr == MAP_FAILED) {
            ::close(shm_fd_);
            shm_fd_ = -1;
            return false;
        }
#endif

        header_ = reinterpret_cast<SHMHeader*>(ptr);
        ring_data_ = reinterpret_cast<uint8_t*>(ptr) + sizeof(SHMHeader);

        header_->magic = SHM_MAGIC;
        header_->version = 1;
        header_->capacity = SHM_RING_CAPACITY;
        header_->flags = 0;
        header_->write_cursor.store(0, std::memory_order_relaxed);
        header_->read_cursor.store(0, std::memory_order_relaxed);
        header_->message_sequence.store(0, std::memory_order_relaxed);

        is_connected_ = true;
        return true;
    }

    bool write_message(std::string_view payload) {
        if (!is_connected_ || !header_) return false;

        uint32_t len = static_cast<uint32_t>(payload.size());
        if (len + 4 > SHM_RING_CAPACITY / 2) return false; // Packet too large for ring

        uint64_t current_write = header_->write_cursor.load(std::memory_order_relaxed);
        uint64_t current_read = header_->read_cursor.load(std::memory_order_acquire);

        // Check remaining space
        if ((current_write - current_read) + len + 4 > SHM_RING_CAPACITY) {
            return false; // Ring buffer full (backpressure)
        }

        // Write length prefix followed by payload (handling ring wrap)
        uint8_t len_bytes[4];
        std::memcpy(len_bytes, &len, 4);

        for (int i = 0; i < 4; ++i) {
            ring_data_[(current_write + i) % SHM_RING_CAPACITY] = len_bytes[i];
        }

        for (uint32_t i = 0; i < len; ++i) {
            ring_data_[(current_write + 4 + i) % SHM_RING_CAPACITY] = static_cast<uint8_t>(payload[i]);
        }

        header_->write_cursor.store(current_write + 4 + len, std::memory_order_release);
        header_->message_sequence.fetch_add(1, std::memory_order_relaxed);
        return true;
    }

    bool read_message(std::string& out_payload) {
        if (!is_connected_ || !header_) return false;

        uint64_t current_read = header_->read_cursor.load(std::memory_order_relaxed);
        uint64_t current_write = header_->write_cursor.load(std::memory_order_acquire);

        if (current_read >= current_write) {
            return false; // No new messages
        }

        // Read 4-byte length prefix
        uint8_t len_bytes[4];
        for (int i = 0; i < 4; ++i) {
            len_bytes[i] = ring_data_[(current_read + i) % SHM_RING_CAPACITY];
        }

        uint32_t len = 0;
        std::memcpy(&len, len_bytes, 4);

        if (len > SHM_RING_CAPACITY / 2) {
            // Corrupt or desynchronized header, fast-forward
            header_->read_cursor.store(current_write, std::memory_order_release);
            return false;
        }

        out_payload.resize(len);
        for (uint32_t i = 0; i < len; ++i) {
            out_payload[i] = static_cast<char>(ring_data_[(current_read + 4 + i) % SHM_RING_CAPACITY]);
        }

        header_->read_cursor.store(current_read + 4 + len, std::memory_order_release);
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
            size_t total_size = sizeof(SHMHeader) + SHM_RING_CAPACITY;
            munmap(header_, total_size);
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
