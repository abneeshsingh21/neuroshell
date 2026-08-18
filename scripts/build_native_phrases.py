# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""
Generator script to compile the 2,588+ phrase dictionary and extended system phrases
directly into native C++20 lookup tables in cpp_engine/launcher/native_phrases.hpp.
"""

import os
from pathlib import Path
from intelligence._phrase_data import PHRASES

win_wifi_table = r'powershell -NoProfile -Command "$p=(netsh wlan show profiles)|Select-String \"All User Profile\s*:\s*(.+)$\"|%{ $_.Matches.Groups[1].Value.Trim() }; $r=foreach($n in $p){ $o=netsh wlan show profile name=\"$n\" key=clear 2>$null; $m=$o|Select-String \"Key Content\s*:\s*(.+)$\"; [PSCustomObject]@{ \"Wi-Fi Network (SSID)\" = $n; \"Password\" = if($m){ $m.Matches.Groups[1].Value.Trim() }else{ \"[Open Network]\" } } }; $r|Format-Table -AutoSize"'

additional_phrases = [
    # Wi-Fi & Wireless (Clean Structured Table)
    ("show wifi passwords", win_wifi_table, "sudo nmcli device wifi show-password 2>/dev/null || sudo grep -r '^psk=' /etc/NetworkManager/system-connections/"),
    ("show wifi password", win_wifi_table, "sudo nmcli device wifi show-password"),
    ("wifi passwords", win_wifi_table, "sudo nmcli device wifi show-password"),
    ("wifi password", win_wifi_table, "sudo nmcli device wifi show-password"),
    ("get wifi password", win_wifi_table, "sudo nmcli device wifi show-password"),
    ("get wifi passwords", win_wifi_table, "sudo nmcli device wifi show-password"),
    ("view wifi passwords", win_wifi_table, "sudo nmcli device wifi show-password"),
    ("view wifi password", win_wifi_table, "sudo nmcli device wifi show-password"),
    ("check wifi passwords", win_wifi_table, "sudo nmcli device wifi show-password"),
    ("check wifi password", win_wifi_table, "sudo nmcli device wifi show-password"),
    ("list wifi passwords", win_wifi_table, "nmcli connection show"),
    ("show wifi profiles", win_wifi_table, "nmcli connection show"),
    ("show wifi networks", "netsh wlan show networks", "nmcli dev wifi list"),
    ("list wifi networks", "netsh wlan show networks", "nmcli dev wifi list"),
    ("scan wifi", "netsh wlan show networks mode=bssid", "nmcli dev wifi rescan && nmcli dev wifi list"),
    ("wifi status", "netsh wlan show interfaces", "nmcli radio wifi"),
    ("turn wifi on", "netsh interface set interface \"Wi-Fi\" enabled", "nmcli radio wifi on"),
    ("turn wifi off", "netsh interface set interface \"Wi-Fi\" disabled", "nmcli radio wifi off"),
    ("restart wifi", "netsh interface set interface \"Wi-Fi\" disabled && netsh interface set interface \"Wi-Fi\" enabled", "nmcli radio wifi off && nmcli radio wifi on"),

    # IP & Network
    ("my public ip", "curl -s https://ifconfig.me", "curl -s https://ifconfig.me"),
    ("what is my public ip", "curl -s https://ifconfig.me", "curl -s https://ifconfig.me"),
    ("show public ip", "curl -s https://ifconfig.me", "curl -s https://ifconfig.me"),
    ("show local ip", "ipconfig", "ip a || ifconfig"),
    ("what is my ip", "ipconfig", "ip a || ifconfig"),
    ("show ip address", "ipconfig", "ip a || ifconfig"),
    ("my ip", "ipconfig", "ip a || ifconfig"),
    ("show dns servers", "ipconfig /all | findstr /i \"DNS Servers\"", "cat /etc/resolv.conf"),
    ("flush dns", "ipconfig /flushdns", "sudo systemd-resolve --flush-caches 2>/dev/null || sudo resolvectl flush-caches 2>/dev/null || sudo killall -HUP mDNSResponder"),
    ("clear dns cache", "ipconfig /flushdns", "sudo systemctl restart systemd-resolved 2>/dev/null || sudo killall -HUP mDNSResponder"),
    ("ping google", "ping 8.8.8.8", "ping -c 4 8.8.8.8"),
    ("test internet speed", "curl -s -w \"Download Speed: %{speed_download} bps\\n\" -o NUL https://speed.cloudflare.com/__down?bytes=25000000", "curl -s -w \"Download Speed: %{speed_download} bps\\n\" -o /dev/null https://speed.cloudflare.com/__down?bytes=25000000"),

    # Ports & Connections
    ("show open ports", "netstat -ano | findstr LISTENING", "ss -tuln || netstat -tuln"),
    ("list listening ports", "netstat -ano | findstr LISTENING", "ss -tuln || netstat -tuln"),
    ("open ports", "netstat -ano | findstr LISTENING", "ss -tuln || netstat -tuln"),
    ("active connections", "netstat -ano", "ss -s || netstat -an"),
    ("show routing table", "route print", "ip route || netstat -rn"),

    # System & Hardware
    ("system specs", "systeminfo", "uname -a && lscpu 2>/dev/null || sw_vers"),
    ("show cpu info", "wmic cpu get name,numberofcores,maxclockspeed", "lscpu || sysctl -n machdep.cpu.brand_string"),
    ("show ram info", "wmic memorychip get capacity,speed,manufacturer", "free -h || vm_stat"),
    ("show disk space", "wmic logicaldisk get size,freespace,caption", "df -h"),
    ("battery health", "powershell -Command \"Get-WmiObject -Class Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus\"", "upower -i /org/freedesktop/UPower/devices/battery_BAT0 2>/dev/null || pmset -g batt"),
    ("show gpu info", "wmic path win32_VideoController get name", "nvidia-smi 2>/dev/null || lspci | grep -i vga"),
    ("reboot system", "shutdown /r /t 0", "sudo reboot"),
    ("shutdown system", "shutdown /s /t 0", "sudo poweroff"),

    # Task & Processes
    ("show top processes", "tasklist /v | sort /r /k 5", "top -b -n 1 | head -n 20 || ps aux --sort=-%cpu | head -n 20"),
    ("list running processes", "tasklist", "ps aux"),
]

all_phrases = PHRASES + additional_phrases

def escape_cpp(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")

out_hpp = Path("cpp_engine") / "launcher" / "native_phrases.hpp"
with open(out_hpp, "w", encoding="utf-8") as f:
    f.write("// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.\n")
    f.write("// Auto-generated Native Fast NLP Phrase Dictionary for NeuroShell C++ Host.\n")
    f.write("#pragma once\n\n")
    f.write("#include <string>\n")
    f.write("#include <string_view>\n")
    f.write("#include <unordered_map>\n")
    f.write("#include <vector>\n")
    f.write("#include <algorithm>\n")
    f.write("#include <cctype>\n\n")
    f.write("namespace neuroshell {\n\n")
    f.write("struct PhraseEntry {\n")
    f.write("    const char* win_cmd;\n")
    f.write("    const char* unix_cmd;\n")
    f.write("};\n\n")
    f.write("class NativePhraseDictionary {\n")
    f.write("private:\n")
    f.write("    std::unordered_map<std::string, PhraseEntry> dictionary_;\n\n")
    f.write("public:\n")
    f.write("    NativePhraseDictionary() {\n")
    f.write(f"        dictionary_.reserve({len(all_phrases) + 200});\n")
    
    seen = set()
    for item in all_phrases:
        phrase = item[0]
        win_cmd = item[1]
        unix_cmd = item[2]
        p_clean = phrase.strip().lower()
        if not p_clean or p_clean in seen:
            continue
        seen.add(p_clean)
        f.write(f'        dictionary_["{escape_cpp(p_clean)}"] = PhraseEntry{{"{escape_cpp(win_cmd)}", "{escape_cpp(unix_cmd)}" }};\n')

    f.write("    }\n\n")
    f.write("    std::string Lookup(std::string_view english_query, bool is_windows = true) const {\n")
    f.write("        std::string lower(english_query);\n")
    f.write("        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);\n")
    f.write("        size_t s = lower.find_first_not_of(\" \\t\\r\\n\");\n")
    f.write("        if (s == std::string::npos) return \"\";\n")
    f.write("        size_t e = lower.find_last_not_of(\" \\t\\r\\n\");\n")
    f.write("        lower = lower.substr(s, e - s + 1);\n\n")
    f.write("        // 1. Direct O(1) exact match\n")
    f.write("        auto it = dictionary_.find(lower);\n")
    f.write("        if (it != dictionary_.end()) {\n")
    f.write("            return is_windows ? it->second.win_cmd : it->second.unix_cmd;\n")
    f.write("        }\n\n")
    f.write("        // 2. Strip conversational prefixes\n")
    f.write("        const std::vector<std::string> prefixes = {\n")
    f.write("            \"please \", \"can you \", \"how to \", \"i want to \", \"cmd to \",\n")
    f.write("            \"command to \", \"tell me \", \"neuroshell \", \"give me \", \"show me \"\n")
    f.write("        };\n")
    f.write("        for (const auto& pfx : prefixes) {\n")
    f.write("            if (lower.rfind(pfx, 0) == 0) {\n")
    f.write("                std::string stripped = lower.substr(pfx.length());\n")
    f.write("                auto it2 = dictionary_.find(stripped);\n")
    f.write("                if (it2 != dictionary_.end()) {\n")
    f.write("                    return is_windows ? it2->second.win_cmd : it2->second.unix_cmd;\n")
    f.write("                }\n")
    f.write("            }\n")
    f.write("        }\n\n")
    f.write("        return \"\";\n")
    f.write("    }\n\n")
    f.write("    size_t size() const { return dictionary_.size(); }\n")
    f.write("};\n\n")
    f.write("} // namespace neuroshell\n")

print(f"Generated {out_hpp} with {len(seen)} unique phrases.")
