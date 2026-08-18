// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
#pragma once

#include <string>
#include <vector>
#include <iostream>
#include <algorithm>
#include <functional>

namespace neuroshell {

struct PaletteCommand {
    std::string title;
    std::string description;
    std::string category;
    std::string action_command;
};

class InTerminalCommandPalette {
private:
    std::vector<PaletteCommand> commands_;

public:
    InTerminalCommandPalette() {
        commands_ = {
            {"🎨 Switch Theme", "Change TrueColor ANSI color scheme", "Appearance", "/theme"},
            {"🔑 Configure API Key", "Interactive AES-128 key setup for Groq/OpenAI/Claude", "LLM", "/api-key"},
            {"🤖 Model Selector", "Switch active LLM model (Llama-3.3, GPT-4o, Claude)", "LLM", "/model"},
            {"🛡️ Viewport Secret DLP Status", "Inspect real-time credential masking engine", "Security", "/dlp"},
            {"🔓 Toggle Secret Unmask", "Temporarily reveal/hide masked credentials", "Security", "/unmask"},
            {"🪟 Vertical Split Pane", "Split viewport vertically (side-by-side terminal)", "Layout", "/vsplit"},
            {"🪟 Horizontal Split Pane", "Split viewport horizontally (stacked terminal)", "Layout", "/hsplit"},
            {"📡 Broadcast Cluster Command", "Run command simultaneously across all split panes", "Swarm", "@cluster "},
            {"💾 Export Session Recording", "Save 50k-line session to Asciinema v2 (.cast)", "Audit", "/export-session"},
            {"🔖 Saved Directory Bookmarks", "List all pinned folder bookmarks", "Navigation", "bookmarks"},
            {"🌐 Show Wi-Fi Passwords", "Display clean table of all saved Wi-Fi keys", "DevOps", "show wifi passwords"},
            {"🔌 Show Open Ports", "List all active TCP listening sockets", "DevOps", "show open ports"},
            {"⚡ Parallel Task Supervisor", "View running background services and worker statuses", "Tasks", "/tasks"},
            {"🧪 Parallel Test Runner", "Run project test suite across all CPU cores", "Testing", "@test"},
            {"🎯 Test Modified Files", "Run tests only for files changed in git", "Testing", "@test changed"},
            {"🧹 Clear Screen & Redraw", "Clear console viewport and display banner", "Display", "clear"},
            {"❓ Comprehensive Help Directory", "View complete shortcut and command reference", "Help", "/help"},
            {"🚪 Exit NeuroShell", "Gracefully terminate terminal session", "System", "exit"}
        };
    }

    const std::vector<PaletteCommand>& GetAllCommands() const {
        return commands_;
    }

    std::vector<PaletteCommand> Search(const std::string& query) const {
        if (query.empty()) return commands_;
        std::string lowerQ = query;
        std::transform(lowerQ.begin(), lowerQ.end(), lowerQ.begin(), ::tolower);

        std::vector<PaletteCommand> results;
        for (const auto& cmd : commands_) {
            std::string lowerTitle = cmd.title;
            std::string lowerDesc = cmd.description;
            std::string lowerCat = cmd.category;
            std::string lowerAction = cmd.action_command;
            std::transform(lowerTitle.begin(), lowerTitle.end(), lowerTitle.begin(), ::tolower);
            std::transform(lowerDesc.begin(), lowerDesc.end(), lowerDesc.begin(), ::tolower);
            std::transform(lowerCat.begin(), lowerCat.end(), lowerCat.begin(), ::tolower);
            std::transform(lowerAction.begin(), lowerAction.end(), lowerAction.begin(), ::tolower);

            if (lowerTitle.find(lowerQ) != std::string::npos ||
                lowerDesc.find(lowerQ) != std::string::npos ||
                lowerCat.find(lowerQ) != std::string::npos ||
                lowerAction.find(lowerQ) != std::string::npos) {
                results.push_back(cmd);
            }
        }
        return results;
    }
};

} // namespace neuroshell
