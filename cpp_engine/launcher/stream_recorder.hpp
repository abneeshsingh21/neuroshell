// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
#pragma once

#include <string>
#include <vector>
#include <deque>
#include <chrono>
#include <mutex>
#include <fstream>
#include <sstream>
#include <iostream>

namespace neuroshell {

struct StreamChunk {
    uint64_t timestamp_us;
    std::string data;
    bool is_input;
};

class StreamRecorder {
private:
    std::deque<StreamChunk> ring_buffer_;
    size_t max_chunks_{50000};
    mutable std::mutex record_mutex_;
    std::chrono::steady_clock::time_point start_time_;
    bool recording_enabled_{true};

public:
    StreamRecorder(size_t max_chunks = 50000)
        : max_chunks_(max_chunks), start_time_(std::chrono::steady_clock::now()) {}

    void record_output(const std::string& data) {
        if (!recording_enabled_ || data.empty()) return;
        auto now = std::chrono::steady_clock::now();
        uint64_t us = std::chrono::duration_cast<std::chrono::microseconds>(now - start_time_).count();

        std::lock_guard<std::mutex> lock(record_mutex_);
        if (ring_buffer_.size() >= max_chunks_) {
            ring_buffer_.pop_front();
        }
        ring_buffer_.push_back({us, data, false});
    }

    void record_input(const std::string& data) {
        if (!recording_enabled_ || data.empty()) return;
        auto now = std::chrono::steady_clock::now();
        uint64_t us = std::chrono::duration_cast<std::chrono::microseconds>(now - start_time_).count();

        std::lock_guard<std::mutex> lock(record_mutex_);
        if (ring_buffer_.size() >= max_chunks_) {
            ring_buffer_.pop_front();
        }
        ring_buffer_.push_back({us, data, true});
    }

    size_t get_total_chunks() const {
        std::lock_guard<std::mutex> lock(record_mutex_);
        return ring_buffer_.size();
    }

    // Export session to standard asciinema v2 (.cast) format
    bool export_asciinema(const std::string& file_path, int width = 120, int height = 35) const {
        std::lock_guard<std::mutex> lock(record_mutex_);
        std::ofstream out(file_path, std::ios::out | std::ios::trunc);
        if (!out.is_open()) return false;

        // Write asciinema header JSON
        out << "{\"version\": 2, \"width\": " << width << ", \"height\": " << height
            << ", \"timestamp\": " << std::time(nullptr)
            << ", \"title\": \"NeuroShell Enterprise Session\", \"env\": {\"SHELL\": \"neuroshell\"}}\n";

        for (const auto& chunk : ring_buffer_) {
            double sec = static_cast<double>(chunk.timestamp_us) / 1000000.0;
            // Escape JSON string for chunk data
            std::ostringstream json_escaped;
            for (char c : chunk.data) {
                if (c == '"') json_escaped << "\\\"";
                else if (c == '\\') json_escaped << "\\\\";
                else if (c == '\b') json_escaped << "\\b";
                else if (c == '\f') json_escaped << "\\f";
                else if (c == '\n') json_escaped << "\\n";
                else if (c == '\r') json_escaped << "\\r";
                else if (c == '\t') json_escaped << "\\t";
                else if (static_cast<unsigned char>(c) < 32) {
                    json_escaped << "\\u00" << (c < 16 ? "0" : "") << std::hex << (int)(unsigned char)c << std::dec;
                } else {
                    json_escaped << c;
                }
            }

            out << "[" << sec << ", \"" << (chunk.is_input ? "i" : "o") << "\", \"" << json_escaped.str() << "\"]\n";
        }

        return true;
    }

    // Interactive Visual Time-Travel UI Renderer
    void render_time_travel_scrubber(int current_idx, int total) const {
        std::cout << "\x1b[s"; // Save cursor position
        std::cout << "\x1b[999;1H"; // Move to bottom row
        std::cout << "\x1b[48;5;236;97;1m ⏪ TIME-TRAVEL SCRUBBER [";

        int bar_width = 30;
        int filled = total > 0 ? (current_idx * bar_width) / total : 0;
        for (int i = 0; i < bar_width; ++i) {
            if (i < filled) std::cout << "█";
            else if (i == filled) std::cout << "◆";
            else std::cout << "░";
        }

        std::cout << "] " << current_idx << "/" << total << " (Press ←/→ to scrub, Enter to exit) \x1b[0m";
        std::cout << "\x1b[u"; // Restore cursor position
        std::cout.flush();
    }
};

} // namespace neuroshell
