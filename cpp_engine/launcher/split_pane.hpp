// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
#pragma once

#include <vector>
#include <string>
#include <memory>
#include <iostream>
#include "pty_host.hpp"

namespace neuroshell {

enum class SplitOrientation {
    NONE,
    VERTICAL,    // Side-by-side (|)
    HORIZONTAL   // Stacked top/bottom (-)
};

struct Pane {
    int id;
    std::string title;
    std::string cwd;
    bool is_active{false};
    std::unique_ptr<NeuroShell::PTY::PseudoTerminalHost> pty;

    Pane(int pane_id, const std::string& start_cwd = ".")
        : id(pane_id), title("Pane #" + std::to_string(pane_id)), cwd(start_cwd) {
        pty = std::make_unique<NeuroShell::PTY::PseudoTerminalHost>();
    }
};

class SplitPaneManager {
private:
    std::vector<std::unique_ptr<Pane>> panes_;
    int active_pane_index_{0};
    int next_pane_id_{1};
    SplitOrientation current_split_{SplitOrientation::NONE};

public:
    SplitPaneManager() {
        // Initial primary pane
        panes_.push_back(std::make_unique<Pane>(next_pane_id_++));
        panes_[0]->is_active = true;
    }

    size_t get_pane_count() const { return panes_.size(); }
    int get_active_index() const { return active_pane_index_; }

    Pane* get_active_pane() {
        if (panes_.empty()) return nullptr;
        if (active_pane_index_ >= static_cast<int>(panes_.size())) {
            active_pane_index_ = 0;
        }
        return panes_[active_pane_index_].get();
    }

    bool split_vertical(const std::string& cwd = ".") {
        if (panes_.size() >= 4) {
            std::cout << "\r\n\x1b[33m⚠ Maximum 4 split panes supported in terminal viewport.\x1b[0m\r\n";
            return false;
        }

        auto new_pane = std::make_unique<Pane>(next_pane_id_++, cwd);
        panes_.push_back(std::move(new_pane));
        current_split_ = SplitOrientation::VERTICAL;
        set_active_pane(static_cast<int>(panes_.size()) - 1);
        render_pane_bar();
        return true;
    }

    bool split_horizontal(const std::string& cwd = ".") {
        if (panes_.size() >= 4) {
            std::cout << "\r\n\x1b[33m⚠ Maximum 4 split panes supported in terminal viewport.\x1b[0m\r\n";
            return false;
        }

        auto new_pane = std::make_unique<Pane>(next_pane_id_++, cwd);
        panes_.push_back(std::move(new_pane));
        current_split_ = SplitOrientation::HORIZONTAL;
        set_active_pane(static_cast<int>(panes_.size()) - 1);
        render_pane_bar();
        return true;
    }

    void close_active_pane() {
        if (panes_.size() <= 1) return; // Keep at least one pane

        panes_.erase(panes_.begin() + active_pane_index_);
        if (active_pane_index_ >= static_cast<int>(panes_.size())) {
            active_pane_index_ = static_cast<int>(panes_.size()) - 1;
        }
        set_active_pane(active_pane_index_);
        render_pane_bar();
    }

    void set_active_pane(int index) {
        if (index < 0 || index >= static_cast<int>(panes_.size())) return;
        for (size_t i = 0; i < panes_.size(); ++i) {
            panes_[i]->is_active = (static_cast<int>(i) == index);
        }
        active_pane_index_ = index;
    }

    void next_pane() {
        if (panes_.empty()) return;
        set_active_pane((active_pane_index_ + 1) % panes_.size());
        render_pane_bar();
    }

    void prev_pane() {
        if (panes_.empty()) return;
        set_active_pane((active_pane_index_ - 1 + static_cast<int>(panes_.size())) % panes_.size());
        render_pane_bar();
    }

    // Broadcast a single command to all split panes simultaneously
    void broadcast_command(const std::string& cmd) {
        std::cout << "\r\n\x1b[35;1m⌬ BROADCASTING TO " << panes_.size() << " PANES: \x1b[0m" << cmd << "\r\n";
        for (auto& pane : panes_) {
            if (pane->pty && pane->pty->IsActive()) {
                pane->pty->WriteInput(cmd + "\r\n");
            }
        }
    }

    void render_pane_bar() const {
        std::cout << "\x1b[s"; // Save cursor
        std::cout << "\x1b[1;1H"; // Top line
        std::cout << "\x1b[48;5;235;97m ⌬ PANES: ";

        for (size_t i = 0; i < panes_.size(); ++i) {
            if (panes_[i]->is_active) {
                std::cout << "\x1b[48;5;33;97;1m [" << (i + 1) << ": " << panes_[i]->title << "] \x1b[48;5;235;97m ";
            } else {
                std::cout << "\x1b[90m [" << (i + 1) << ": " << panes_[i]->title << "] \x1b[97m ";
            }
        }

        std::cout << "\x1b[0m";
        std::cout << "\x1b[u"; // Restore cursor
        std::cout.flush();
    }
};

} // namespace neuroshell
