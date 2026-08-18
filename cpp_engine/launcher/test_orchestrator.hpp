// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
#pragma once

#include <string>
#include <vector>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <cstdlib>
#include <chrono>
#include <algorithm>

namespace fs = std::filesystem;

namespace neuroshell {

enum class ProjectEcosystem {
    Python,
    NodeTypeScript,
    Rust,
    Go,
    Cpp,
    Unknown
};

class TestOrchestrator {
public:
    static ProjectEcosystem DetectEcosystem(const fs::path& root = fs::current_path()) {
        if (fs::exists(root / "pyproject.toml") || fs::exists(root / "requirements.txt") || fs::exists(root / "pytest.ini") || fs::exists(root / "setup.py")) {
            return ProjectEcosystem::Python;
        }
        if (fs::exists(root / "package.json")) {
            return ProjectEcosystem::NodeTypeScript;
        }
        if (fs::exists(root / "Cargo.toml")) {
            return ProjectEcosystem::Rust;
        }
        if (fs::exists(root / "go.mod")) {
            return ProjectEcosystem::Go;
        }
        if (fs::exists(root / "CMakeLists.txt")) {
            return ProjectEcosystem::Cpp;
        }
        return ProjectEcosystem::Unknown;
    }

    static std::string GetParallelTestCommand(const std::vector<std::string>& files = {}, const fs::path& root = fs::current_path()) {
        ProjectEcosystem eco = DetectEcosystem(root);
        std::string fileList = "";
        for (const auto& f : files) {
            fileList += " " + f;
        }

        switch (eco) {
            case ProjectEcosystem::Python:
                if (!files.empty()) {
                    return "pytest -n auto -v" + fileList;
                }
                return "pytest -n auto -v";

            case ProjectEcosystem::NodeTypeScript:
                if (fs::exists(root / "vitest.config.ts") || fs::exists(root / "vitest.config.js")) {
                    return "npx vitest run --threads" + fileList;
                }
                if (!files.empty()) {
                    return "npm test --" + fileList;
                }
                return "npm test -- --maxWorkers=50%";

            case ProjectEcosystem::Rust:
                return "cargo nextest run || cargo test";

            case ProjectEcosystem::Go:
                return "go test -p 4 -v ./...";

            case ProjectEcosystem::Cpp:
                return "ctest -j 4 --output-on-failure";

            default:
                if (!files.empty()) {
                    return "pytest -v" + fileList;
                }
                return "pytest -v";
        }
    }

    static std::vector<std::string> GetChangedTestFiles() {
        std::vector<std::string> testFiles;
        std::string gitCmd = "git status --porcelain 2>&1";

#if defined(_WIN32)
        FILE* pipe = _popen(gitCmd.c_str(), "r");
#else
        FILE* pipe = popen(gitCmd.c_str(), "r");
#endif
        if (!pipe) return testFiles;

        char buffer[512];
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            std::string line(buffer);
            size_t s = line.find_first_not_of(" \t\r\n");
            if (s != std::string::npos && line.length() > 3) {
                std::string filePath = line.substr(3);
                // trim
                size_t fe = filePath.find_last_not_of(" \t\r\n\"");
                if (fe != std::string::npos) filePath = filePath.substr(0, fe + 1);
                
                if (filePath.find("test") != std::string::npos) {
                    testFiles.push_back(filePath);
                } else {
                    // Try to infer test file
                    fs::path p(filePath);
                    std::string stem = p.stem().string();
                    std::string ext = p.extension().string();
                    std::string candidate1 = "tests/test_" + stem + ext;
                    std::string candidate2 = "tests/" + stem + ".test" + ext;
                    if (fs::exists(candidate1)) testFiles.push_back(candidate1);
                    else if (fs::exists(candidate2)) testFiles.push_back(candidate2);
                }
            }
        }

#if defined(_WIN32)
        _pclose(pipe);
#else
        pclose(pipe);
#endif
        return testFiles;
    }
};

} // namespace neuroshell
