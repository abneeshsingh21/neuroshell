// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Licensed under the Apache License, Version 2.0 (the "License").
#pragma once

#include <string>
#include <string_view>
#include <vector>
#include <regex>
#include <algorithm>
#include <sstream>

namespace neuroshell {

struct ParameterRule {
    std::regex pattern;
    std::string win_template;
    std::string unix_template;
    std::vector<std::string> slot_names;
};

class ASTParameterExtractor {
private:
    std::vector<ParameterRule> rules_;

public:
    ASTParameterExtractor() {
        // 1. Files larger than {size} in {path}
        // e.g. "find files larger than 50MB in src"
        rules_.push_back({
            std::regex(R"(find\s+files\s+larger\s+than\s+([0-9]+(?:\.[0-9]+)?(?:kb|mb|gb|b)?)\s+in\s+([^\s]+))", std::regex::icase),
            R"(powershell -NoProfile -Command "Get-ChildItem -Path '$2' -Recurse -File | Where-Object { $_.Length -gt $1 } | Select-Object FullName, @{Name='Size(MB)';Expression={[math]::Round($_.Length/1MB,2)}} | Format-Table -AutoSize")",
            R"(find "$2" -type f -size +$1 -exec ls -lh {} +)",
            {"size", "path"}
        });

        // 2. Delete git branches merged into {branch}
        // e.g. "delete branches merged into main"
        rules_.push_back({
            std::regex(R"(delete\s+(?:git\s+)?branches\s+merged\s+into\s+([^\s]+))", std::regex::icase),
            R"(powershell -NoProfile -Command "git branch --merged $1 | Select-String -NotMatch '^\*|\b$1\b' | ForEach-Object { git branch -d $_.ToString().Trim() }")",
            R"(git branch --merged "$1" | grep -v "^\*" | grep -v "$1" | xargs -r git branch -d)",
            {"branch"}
        });

        // 3. Docker logs for container {name} last {n} lines
        // e.g. "docker logs for container web last 100 lines" or "show logs for api last 50 lines"
        rules_.push_back({
            std::regex(R"((?:show\s+)?(?:docker\s+)?logs\s+(?:for\s+)?(?:container\s+)?([^\s]+)\s+last\s+([0-9]+)\s+lines)", std::regex::icase),
            R"(docker logs --tail $2 -f $1)",
            R"(docker logs --tail $2 -f $1)",
            {"name", "lines"}
        });

        // 4. Compress / Zip folder {dir} to {zip}
        // e.g. "compress folder dist to release.zip" or "zip src to backup.zip"
        rules_.push_back({
            std::regex(R"((?:compress|zip)\s+(?:folder\s+|directory\s+)?([^\s]+)\s+to\s+([^\s]+))", std::regex::icase),
            R"(powershell -NoProfile -Command "Compress-Archive -Path '$1' -DestinationPath '$2' -Force")",
            R"(zip -r "$2" "$1")",
            {"dir", "zip"}
        });

        // 5. Extract / Unzip archive {zip} to {dir}
        // e.g. "extract bundle.zip to output" or "unzip package.zip to dist"
        rules_.push_back({
            std::regex(R"((?:extract|unzip)\s+([^\s]+)\s+to\s+([^\s]+))", std::regex::icase),
            R"(powershell -NoProfile -Command "Expand-Archive -Path '$1' -DestinationPath '$2' -Force")",
            R"(unzip -o "$1" -d "$2" || tar -xzf "$1" -C "$2")",
            {"zip", "dir"}
        });

        // 6. Kill / Free port {port}
        // e.g. "kill process on port 8080" or "free port 3000"
        rules_.push_back({
            std::regex(R"((?:kill|free|terminate|release)\s+(?:process\s+)?(?:on\s+)?port\s+([0-9]+))", std::regex::icase),
            R"(powershell -NoProfile -Command "$conn = Get-NetTCPConnection -LocalPort $1 -ErrorAction SilentlyContinue; if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Write-Host 'Killed PID' $conn.OwningProcess 'on port $1' } else { Write-Host 'Port $1 is already free' }")",
            R"(fuser -k $1/tcp 2>/dev/null || lsof -ti:$1 | xargs -r kill -9 2>/dev/null)",
            {"port"}
        });

        // 7. Find files with extension {ext} containing {query}
        // e.g. "find in python files import torch" or "search in js files express"
        rules_.push_back({
            std::regex(R"((?:find|search)\s+in\s+([^\s]+)\s+files\s+(.+))", std::regex::icase),
            R"(powershell -NoProfile -Command "Get-ChildItem -Recurse -Include *.$1 | Select-String '$2'")",
            R"(grep -rn --include="*.$1" "$2" .)",
            {"ext", "query"}
        });

        // 8. Count lines of code in {ext} files
        // e.g. "count lines in py files" or "line count in cpp files"
        rules_.push_back({
            std::regex(R"((?:count\s+lines|line\s+count)\s+(?:of\s+code\s+)?in\s+([^\s]+)\s+files)", std::regex::icase),
            R"(powershell -NoProfile -Command "(Get-Content (Get-ChildItem -Recurse -Include *.$1) | Measure-Object -Line).Lines")",
            R"(find . -name "*.$1" | xargs wc -l)",
            {"ext"}
        });

        // 9. Ping latency test
        // e.g. "ping latency to 8.8.8.8" or "test latency to google.com"
        rules_.push_back({
            std::regex(R"((?:test\s+latency\s+to|ping\s+latency\s+to|latency\s+to)\s+([^\s]+))", std::regex::icase),
            R"(ping -n 5 $1)",
            R"(ping -c 5 $1)",
            {"host"}
        });

        // 10. Show Wi-Fi password for {ssid}
        // e.g. "show wifi password for Airtel_Shiv"
        rules_.push_back({
            std::regex(R"((?:show\s+|get\s+|view\s+)?wifi\s+password\s+(?:for\s+|of\s+)?["']?([^"']+)["']?)", std::regex::icase),
            R"(powershell -NoProfile -Command "$m = (netsh wlan show profile name='$1' key=clear 2>$null | Select-String 'Key Content\s*:\s*(.+)$'); if ($m) { [PSCustomObject]@{ 'Wi-Fi Network' = '$1'; 'Password' = $m.Matches.Groups[1].Value.Trim() } | Format-List } else { Write-Host 'No password found or Open Network for $1' }")",
            R"(sudo nmcli -s -g 802-11-wireless-security.psk connection show "$1" 2>/dev/null || sudo grep -r '^psk=' /etc/NetworkManager/system-connections/"$1".nmconnection 2>/dev/null || security find-generic-password -ga "$1" -w 2>/dev/null)",
            {"ssid"}
        });

        // 11. Service status / restart / logs
        // e.g. "status of service nginx" or "restart service docker"
        rules_.push_back({
            std::regex(R"((?:status\s+of\s+service|service\s+status|check\s+service)\s+([^\s]+))", std::regex::icase),
            R"(powershell -NoProfile -Command "Get-Service -Name '$1' -ErrorAction SilentlyContinue | Format-Table -AutoSize")",
            R"(systemctl status "$1" 2>/dev/null || brew services info "$1" 2>/dev/null || launchctl list | grep "$1")",
            {"service"}
        });

        rules_.push_back({
            std::regex(R"((?:restart\s+service|restart)\s+([^\s]+))", std::regex::icase),
            R"(powershell -NoProfile -Command "Restart-Service -Name '$1' -Force")",
            R"(sudo systemctl restart "$1" 2>/dev/null || brew services restart "$1" 2>/dev/null)",
            {"service"}
        });

        rules_.push_back({
            std::regex(R"((?:logs\s+for\s+service|service\s+logs)\s+([^\s]+))", std::regex::icase),
            R"(powershell -NoProfile -Command "Get-EventLog -LogName Application -Source '$1' -Newest 50 -ErrorAction SilentlyContinue | Format-Table -AutoSize")",
            R"(journalctl -u "$1" -n 50 -f 2>/dev/null || log show --predicate 'process == "$1"' --info --last 10m)",
            {"service"}
        });

        // 12. Clipboard Copy / Paste
        rules_.push_back({
            std::regex(R"(copy\s+file\s+([^\s]+)\s+to\s+clipboard)", std::regex::icase),
            R"(powershell -NoProfile -Command "Get-Content '$1' | Set-Clipboard")",
            R"(pbcopy < "$1" 2>/dev/null || wl-copy < "$1" 2>/dev/null || xclip -selection clipboard < "$1")",
            {"file"}
        });

        // 13. Disk Usage in directory
        rules_.push_back({
            std::regex(R"((?:disk\s+usage|folder\s+size|directory\s+size)\s+(?:in\s+)?([^\s]+))", std::regex::icase),
            R"(powershell -NoProfile -Command "Get-ChildItem -Path '$1' | Select-Object Name, @{Name='Size(MB)';Expression={[math]::Round($_.Length/1MB,2)}} | Sort-Object 'Size(MB)' -Descending | Format-Table -AutoSize")",
            R"(du -sh "$1"/* 2>/dev/null | sort -hr | head -n 25)",
            {"dir"}
        });
    }

    std::string ExtractAndTransform(std::string_view english_query, bool is_windows = true) const {
        std::string query(english_query);
        // Trim whitespace
        size_t s = query.find_first_not_of(" \t\r\n");
        if (s == std::string::npos) return "";
        size_t e = query.find_last_not_of(" \t\r\n");
        query = query.substr(s, e - s + 1);

        // Strip polite conversational prefixes
        const std::vector<std::string> prefixes = {
            "please ", "can you ", "how to ", "i want to ", "cmd to ",
            "command to ", "tell me ", "neuroshell ", "give me ", "show me "
        };
        for (const auto& pfx : prefixes) {
            std::string lowerQ = query;
            std::transform(lowerQ.begin(), lowerQ.end(), lowerQ.begin(), ::tolower);
            if (lowerQ.rfind(pfx, 0) == 0) {
                query = query.substr(pfx.length());
                break;
            }
        }

        for (const auto& rule : rules_) {
            std::smatch match;
            if (std::regex_match(query, match, rule.pattern)) {
                std::string result = is_windows ? rule.win_template : rule.unix_template;
                for (size_t i = 1; i < match.size(); ++i) {
                    std::string placeholder = "$" + std::to_string(i);
                    std::string val = match[i].str();
                    // Replace all occurrences of placeholder
                    size_t pos = 0;
                    while ((pos = result.find(placeholder, pos)) != std::string::npos) {
                        result.replace(pos, placeholder.length(), val);
                        pos += val.length();
                    }
                }
                return result;
            }
        }

        return "";
    }
};

} // namespace neuroshell
