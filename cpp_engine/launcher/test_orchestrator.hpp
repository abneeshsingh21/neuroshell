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
#include <map>

namespace fs = std::filesystem;

namespace neuroshell {

enum class ProjectEcosystem {
    Python,
    NodeTypeScript,
    Rust,
    Go,
    Cpp,
    Java,
    Unknown
};

struct PolyglotSuite {
    std::string language;
    std::string command;
    std::string directory;
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
        if (fs::exists(root / "pom.xml") || fs::exists(root / "build.gradle")) {
            return ProjectEcosystem::Java;
        }
        return ProjectEcosystem::Unknown;
    }

    static std::vector<PolyglotSuite> DetectAllEcosystems(const fs::path& root = fs::current_path()) {
        std::vector<PolyglotSuite> suites;

        // 1. Check Root
        if (fs::exists(root / "pyproject.toml") || fs::exists(root / "requirements.txt") || fs::exists(root / "pytest.ini") || fs::exists(root / "setup.py")) {
            suites.push_back({"Python", "pytest -n auto -v", "."});
        }
        if (fs::exists(root / "package.json")) {
            std::string cmd = (fs::exists(root / "vitest.config.ts") || fs::exists(root / "vitest.config.js")) ? "npx vitest run --threads" : "npm test";
            suites.push_back({"Node/TypeScript", cmd, "."});
        }
        if (fs::exists(root / "Cargo.toml")) {
            suites.push_back({"Rust", "cargo test", "."});
        }
        if (fs::exists(root / "go.mod")) {
            suites.push_back({"Go", "go test -p 4 -v ./...", "."});
        }
        if (fs::exists(root / "CMakeLists.txt")) {
            suites.push_back({"C++", "ctest -j 4 --output-on-failure", "."});
        }

        // 2. Check immediate subfolders for Monorepo microservices (e.g. ./frontend, ./backend, ./api, ./web)
        try {
            for (const auto& entry : fs::directory_iterator(root)) {
                if (entry.is_directory()) {
                    std::string dirName = entry.path().filename().string();
                    if (dirName.rfind(".", 0) == 0 || dirName == "node_modules" || dirName == ".venv" || dirName == "venv" || dirName == "dist" || dirName == "build") {
                        continue;
                    }

                    fs::path subPath = entry.path();
                    if (fs::exists(subPath / "package.json") && suites.empty()) {
                        std::string cmd = "npm --prefix " + dirName + " test";
                        suites.push_back({"Frontend (" + dirName + ")", cmd, dirName});
                    }
                    if ((fs::exists(subPath / "requirements.txt") || fs::exists(subPath / "pyproject.toml")) && suites.empty()) {
                        std::string cmd = "pytest -n auto -v " + dirName;
                        suites.push_back({"Backend (" + dirName + ")", cmd, dirName});
                    }
                }
            }
        } catch (...) {}

        return suites;
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

            case ProjectEcosystem::Java:
                if (fs::exists(root / "pom.xml")) return "mvn test";
                return "./gradlew test";

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
