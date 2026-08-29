// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
//
// TokenStreamReader — host-side consumer of the SHM token-stream ring
// (Phase 2 of the engineering roadmap, ABI v3).
//
// Data path:
//   daemon (llm.generate_streaming) ──frames──► SHM stream ring ──► here
//
// Responsibilities:
//   * render TOKEN frames incrementally (sub-frame latency; no waiting for
//     the full JSON-RPC response),
//   * discard frames from stale stream ids (a cancelled stream's in-flight
//     tokens must never bleed into the next answer),
//   * cooperative cancellation: publish cancel_stream_id when the user
//     presses Esc; the daemon polls it between tokens,
//   * DLP: tokens can split a secret across frame boundaries, so masking
//     is applied per COMPLETED LINE (carry buffer), exactly like the
//     process-output path — a secret is never printed before masking,
//   * bounded waits: first-token timeout and inter-token stall timeout so
//     a dead daemon can never hang the host.
//
// The reader is transport-only: it neither parses JSON nor trusts frame
// payloads beyond UTF-8 text pass-through into the DLP filter.
#pragma once

#include "shm_ipc.hpp"

#include <atomic>
#include <chrono>
#include <functional>
#include <string>
#include <thread>

namespace neuroshell {

struct StreamResult {
    bool completed = false;   // END frame received
    bool cancelled = false;   // cancelled by user (Esc) or daemon ack
    bool error = false;       // ERROR frame received
    bool timed_out = false;   // first-token / stall deadline exceeded
    std::string full_text;    // concatenated raw tokens (pre-DLP)
    std::string error_message;
    uint32_t tokens = 0;
};

class TokenStreamReader {
public:
    // `emit_line`  — called with each DLP-filtered completed line.
    // `poll_cancel`— non-blocking; returns true when the user requested
    //                cancellation (e.g. Esc pressed). Optional.
    using EmitFn = std::function<void(const std::string&)>;
    using CancelPollFn = std::function<bool()>;

    static constexpr auto kFirstTokenTimeout = std::chrono::milliseconds(30000);
    static constexpr auto kStallTimeout = std::chrono::milliseconds(15000);
    static constexpr auto kPollInterval = std::chrono::milliseconds(2);

    TokenStreamReader(SHMRingBuffer& ring, EmitFn emit_line,
                      CancelPollFn poll_cancel = nullptr)
        : ring_(ring), emit_(std::move(emit_line)), poll_cancel_(std::move(poll_cancel)) {}

    // Allocate the next stream id (monotonic, never 0 — 0 means "no cancel").
    static uint32_t NextStreamId() {
        static std::atomic<uint32_t> counter{0};
        uint32_t id = counter.fetch_add(1, std::memory_order_relaxed) + 1;
        if (id == 0) id = counter.fetch_add(1, std::memory_order_relaxed) + 1;
        return id;
    }

    // Consume frames for `stream_id` until END/ERROR/timeout/cancel.
    // Blocking (with 2ms poll granularity); designed to be called from the
    // interactive command path while a raw-mode key poller feeds
    // `poll_cancel`.
    StreamResult Consume(uint32_t stream_id) {
        StreamResult res;
        std::string line_carry; // partial line awaiting '\n' (DLP boundary)

        auto last_activity = std::chrono::steady_clock::now();
        bool first_token_seen = false;
        bool cancel_sent = false;

        while (true) {
            // 1. User cancellation (Esc) → publish, then keep draining until
            //    the daemon acks with a terminal frame (or times out).
            if (!cancel_sent && poll_cancel_ && poll_cancel_()) {
                ring_.request_cancel(stream_id);
                cancel_sent = true;
                res.cancelled = true;
            }

            // 2. Pull frames.
            SHMRingBuffer::StreamFrame f;
            bool got = ring_.read_frame(f);
            if (got) {
                if (f.stream_id != stream_id) {
                    continue; // stale frame from a previous stream — drop
                }
                last_activity = std::chrono::steady_clock::now();

                switch (f.type) {
                    case StreamFrameType::Token: {
                        first_token_seen = true;
                        ++res.tokens;
                        res.full_text += f.payload;
                        if (!cancel_sent) {
                            line_carry += f.payload;
                            flush_lines(line_carry);
                        }
                        break;
                    }
                    case StreamFrameType::End: {
                        // Daemon signals completion; payload may carry
                        // {"cancelled":true} — reflect it.
                        if (f.payload.find("\"cancelled\": true") != std::string::npos ||
                            f.payload.find("\"cancelled\":true") != std::string::npos) {
                            res.cancelled = true;
                        }
                        if (!line_carry.empty() && !cancel_sent) {
                            emit_(line_carry); // final unterminated line
                            line_carry.clear();
                        }
                        res.completed = true;
                        return res;
                    }
                    case StreamFrameType::Error: {
                        res.error = true;
                        res.error_message = f.payload;
                        return res;
                    }
                }
                continue; // immediately try for the next frame (no sleep)
            }

            // 3. Idle: enforce deadlines, then sleep the poll interval.
            auto idle = std::chrono::steady_clock::now() - last_activity;
            auto limit = first_token_seen ? kStallTimeout : kFirstTokenTimeout;
            if (idle > limit) {
                res.timed_out = true;
                if (!cancel_sent) ring_.request_cancel(stream_id); // stop the producer
                return res;
            }
            std::this_thread::sleep_for(kPollInterval);
        }
    }

private:
    void flush_lines(std::string& carry) {
        size_t nl;
        while ((nl = carry.find('\n')) != std::string::npos) {
            emit_(carry.substr(0, nl));
            carry.erase(0, nl + 1);
        }
    }

    SHMRingBuffer& ring_;
    EmitFn emit_;
    CancelPollFn poll_cancel_;
};

} // namespace neuroshell
