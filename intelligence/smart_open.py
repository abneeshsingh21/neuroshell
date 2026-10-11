# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Smart Open Engine — Advanced Intent Router
Handles "open", "launch", "navigate", "show in explorer", and smart
system actions with fuzzy folder search, app registry, URL inference,
system shortcuts, and file-type search.
"""

import os
import platform
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Ensure neuroshell root is on sys.path regardless of execution CWD
_NEUROSHELL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NEUROSHELL_ROOT not in sys.path:
    sys.path.insert(0, _NEUROSHELL_ROOT)

# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class OpenResult:
    """Result of a smart-open resolution."""
    command: str
    explanation: str
    confidence: float = 0.92
    target_type: str = ""       # folder, file, app, url, system, power
    resolved_path: str = ""     # resolved absolute path (if applicable)
    alternatives: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Windows App Registry
# ═══════════════════════════════════════════════════════════

# Maps common names → (launch_command, display_name)
# NOTE: All Windows app launches use `powershell Start-Process` which works
# correctly from both PowerShell AND CMD shell contexts, unlike `cmd /c start`
# which breaks when the executor is in PowerShell mode.
WINDOWS_APP_REGISTRY: dict[str, tuple[str, str]] = {
    # Browsers
    "chrome": ('powershell -NoProfile -Command "Start-Process chrome"', "Google Chrome"),
    "google chrome": ('powershell -NoProfile -Command "Start-Process chrome"', "Google Chrome"),
    "chrome browser": ('powershell -NoProfile -Command "Start-Process chrome"', "Google Chrome"),
    "chrome brower": ('powershell -NoProfile -Command "Start-Process chrome"', "Google Chrome"),
    "google": ('powershell -NoProfile -Command "Start-Process chrome"', "Google Chrome"),
    "firefox": ('powershell -NoProfile -Command "Start-Process firefox"', "Mozilla Firefox"),
    "edge": ('powershell -NoProfile -Command "Start-Process msedge"', "Microsoft Edge"),
    "microsoft edge": ('powershell -NoProfile -Command "Start-Process msedge"', "Microsoft Edge"),
    "brave": ('powershell -NoProfile -Command "Start-Process brave"', "Brave Browser"),
    "opera": ('powershell -NoProfile -Command "Start-Process opera"', "Opera Browser"),

    # Editors & IDEs
    "vscode": ("code .", "Visual Studio Code"),
    "vs code": ("code .", "Visual Studio Code"),
    "visual studio code": ("code .", "Visual Studio Code"),
    "notepad": ('powershell -NoProfile -Command "Start-Process notepad"', "Notepad"),
    "notepad++": ('powershell -NoProfile -Command "Start-Process notepad++"', "Notepad++"),
    "sublime": ('powershell -NoProfile -Command "Start-Process sublime_text"', "Sublime Text"),
    "pycharm": ('powershell -NoProfile -Command "Start-Process pycharm64"', "PyCharm"),
    "intellij": ('powershell -NoProfile -Command "Start-Process idea64"', "IntelliJ IDEA"),
    "android studio": ('powershell -NoProfile -Command "Start-Process studio64"', "Android Studio"),

    # Communication
    "discord": ('powershell -NoProfile -Command "Start-Process discord"', "Discord"),
    "slack": ('powershell -NoProfile -Command "Start-Process slack"', "Slack"),
    "teams": ('powershell -NoProfile -Command "Start-Process ms-teams"', "Microsoft Teams"),
    "microsoft teams": ('powershell -NoProfile -Command "Start-Process ms-teams"', "Microsoft Teams"),
    "zoom": ('powershell -NoProfile -Command "Start-Process zoom"', "Zoom"),
    "telegram": ('powershell -NoProfile -Command "Start-Process telegram"', "Telegram"),
    "whatsapp": ('powershell -NoProfile -Command "Start-Process whatsapp:"', "WhatsApp"),
    "whatsapp app": ('powershell -NoProfile -Command "Start-Process whatsapp:"', "WhatsApp"),

    # Media
    "spotify": ('powershell -NoProfile -Command "Start-Process spotify:"', "Spotify"),
    "vlc": ('powershell -NoProfile -Command "Start-Process vlc"', "VLC Media Player"),

    # Dev tools
    "terminal": ('powershell -NoProfile -Command "Start-Process wt"', "Windows Terminal"),
    "windows terminal": ('powershell -NoProfile -Command "Start-Process wt"', "Windows Terminal"),
    "powershell": ('powershell -NoProfile -Command "Start-Process powershell"', "PowerShell"),
    "cmd": ('powershell -NoProfile -Command "Start-Process cmd"', "Command Prompt"),
    "command prompt": ('powershell -NoProfile -Command "Start-Process cmd"', "Command Prompt"),
    "git bash": ('powershell -NoProfile -Command "Start-Process git-bash"', "Git Bash"),
    "postman": ('powershell -NoProfile -Command "Start-Process postman"', "Postman"),
    "docker desktop": ('powershell -NoProfile -Command "Start-Process \'Docker Desktop\'"', "Docker Desktop"),

    # Productivity
    "word": ('powershell -NoProfile -Command "Start-Process winword"', "Microsoft Word"),
    "excel": ('powershell -NoProfile -Command "Start-Process excel"', "Microsoft Excel"),
    "powerpoint": ('powershell -NoProfile -Command "Start-Process powerpnt"', "Microsoft PowerPoint"),
    "outlook": ('powershell -NoProfile -Command "Start-Process outlook"', "Microsoft Outlook"),
    "onenote": ('powershell -NoProfile -Command "Start-Process onenote"', "OneNote"),

    # File managers & utils
    "file explorer": ("__EXPLORER_CWD__", "File Explorer"),   # special sentinel — handled by _open_cwd
    "explorer": ("__EXPLORER_CWD__", "File Explorer"),
    "calculator": ('powershell -NoProfile -Command "Start-Process calc"', "Calculator"),
    "paint": ('powershell -NoProfile -Command "Start-Process mspaint"', "Paint"),
    "snipping tool": ('powershell -NoProfile -Command "Start-Process snippingtool"', "Snipping Tool"),
}

# Linux app registry
LINUX_APP_REGISTRY: dict[str, tuple[str, str]] = {
    "chrome": ("google-chrome", "Google Chrome"),
    "firefox": ("firefox", "Firefox"),
    "vscode": ("code .", "VS Code"),
    "vs code": ("code .", "VS Code"),
    "terminal": ("gnome-terminal", "Terminal"),
    "nautilus": ("nautilus .", "Files"),
    "file manager": ("nautilus .", "Files"),
    "calculator": ("gnome-calculator", "Calculator"),
    "spotify": ("spotify", "Spotify"),
    "discord": ("discord", "Discord"),
    "slack": ("slack", "Slack"),
    "vlc": ("vlc", "VLC"),
}


# ═══════════════════════════════════════════════════════════
# Smart URL Inference
# ═══════════════════════════════════════════════════════════

SITE_MAP: dict[str, str] = {
    "github": "https://github.com",
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "reddit": "https://reddit.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "linkedin": "https://linkedin.com",
    "facebook": "https://facebook.com",
    "instagram": "https://instagram.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "gmail": "https://mail.google.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "notion": "https://notion.so",
    "figma": "https://figma.com",
    "vercel": "https://vercel.com",
    "netlify": "https://netlify.com",
    "npm": "https://npmjs.com",
    "pypi": "https://pypi.org",
    "docker hub": "https://hub.docker.com",
    "aws": "https://aws.amazon.com",
    "azure": "https://portal.azure.com",
    "wikipedia": "https://wikipedia.org",
    "medium": "https://medium.com",
    "w3schools": "https://w3schools.com",
    "mdn": "https://developer.mozilla.org",
}


# ═══════════════════════════════════════════════════════════
# Windows System Shortcuts
# ═══════════════════════════════════════════════════════════

SYSTEM_SHORTCUTS: dict[str, tuple[str, str]] = {
    # Settings & Control Panel
    "settings": ('powershell -NoProfile -Command "Start-Process ms-settings:"', "Windows Settings"),
    "control panel": ('powershell -NoProfile -Command "Start-Process control"', "Control Panel"),
    "display settings": ('powershell -NoProfile -Command "Start-Process ms-settings:display"', "Display Settings"),
    "sound settings": ('powershell -NoProfile -Command "Start-Process ms-settings:sound"', "Sound Settings"),
    "network settings": ('powershell -NoProfile -Command "Start-Process ms-settings:network"', "Network Settings"),
    "bluetooth settings": ('powershell -NoProfile -Command "Start-Process ms-settings:bluetooth"', "Bluetooth Settings"),
    "wifi settings": ('powershell -NoProfile -Command "Start-Process ms-settings:network-wifi"', "WiFi Settings"),
    "storage settings": ('powershell -NoProfile -Command "Start-Process ms-settings:storagesense"', "Storage Settings"),
    "apps settings": ('powershell -NoProfile -Command "Start-Process ms-settings:appsfeatures"', "Apps & Features"),
    "default apps": ('powershell -NoProfile -Command "Start-Process ms-settings:defaultapps"', "Default Apps"),
    "privacy settings": ('powershell -NoProfile -Command "Start-Process ms-settings:privacy"', "Privacy Settings"),
    "update settings": ('powershell -NoProfile -Command "Start-Process ms-settings:windowsupdate"', "Windows Update"),
    "personalization": ('powershell -NoProfile -Command "Start-Process ms-settings:personalization"', "Personalization"),
    "about": ('powershell -NoProfile -Command "Start-Process ms-settings:about"', "About PC"),

    # System tools
    "task manager": ("taskmgr", "Task Manager"),
    "device manager": ("devmgmt.msc", "Device Manager"),
    "disk management": ("diskmgmt.msc", "Disk Management"),
    "services": ("services.msc", "Services"),
    "event viewer": ("eventvwr.msc", "Event Viewer"),
    "registry editor": ("regedit", "Registry Editor"),
    "system information": ("msinfo32", "System Information"),
    "resource monitor": ("resmon", "Resource Monitor"),
    "performance monitor": ("perfmon", "Performance Monitor"),
    "computer management": ("compmgmt.msc", "Computer Management"),
    "group policy": ("gpedit.msc", "Group Policy Editor"),
    "disk cleanup": ("cleanmgr", "Disk Cleanup"),
    "defragment": ("dfrgui", "Defragment and Optimize Drives"),
    "firewall": ("wf.msc", "Windows Firewall"),
    "environment variables": ("rundll32.exe sysdm.cpl,EditEnvironmentVariables", "Environment Variables"),
    "system properties": ("sysdm.cpl", "System Properties"),

    # Accessibility
    "magnifier": ("magnify", "Magnifier"),
    "narrator": ("narrator", "Narrator"),
    "on-screen keyboard": ("osk", "On-Screen Keyboard"),
}


# ═══════════════════════════════════════════════════════════
# Windows Power Commands
# ═══════════════════════════════════════════════════════════

POWER_COMMANDS: dict[str, tuple[str, str]] = {
    # System actions
    "lock screen": ("rundll32.exe user32.dll,LockWorkStation", "Lock the screen"),
    "lock computer": ("rundll32.exe user32.dll,LockWorkStation", "Lock the computer"),
    "lock": ("rundll32.exe user32.dll,LockWorkStation", "Lock the screen"),
    "restart computer": ("shutdown /r /t 0", "Restart the computer"),
    "restart": ("shutdown /r /t 0", "Restart the computer"),
    "reboot": ("shutdown /r /t 0", "Restart the computer"),
    "shut down": ("shutdown /s /t 0", "Shut down the computer"),
    "shutdown": ("shutdown /s /t 0", "Shut down the computer"),
    "sign out": ("shutdown /l", "Sign out of Windows"),
    "log out": ("shutdown /l", "Sign out of Windows"),
    "sleep": ("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", "Put computer to sleep"),

    # Utilities
    "empty recycle bin": ("PowerShell -Command \"Clear-RecycleBin -Force -ErrorAction SilentlyContinue\"", "Empty the Recycle Bin"),
    "clear recycle bin": ("PowerShell -Command \"Clear-RecycleBin -Force -ErrorAction SilentlyContinue\"", "Empty the Recycle Bin"),
    "take screenshot": ("snippingtool", "Take a screenshot with Snipping Tool"),
    "screenshot": ("snippingtool", "Take a screenshot"),
    "check battery": ("PowerShell -Command \"Get-WmiObject Win32_Battery | Select EstimatedChargeRemaining, BatteryStatus\"", "Check battery status"),
    "battery status": ("PowerShell -Command \"Get-WmiObject Win32_Battery | Select EstimatedChargeRemaining, BatteryStatus\"", "Check battery status"),
    "what's my ip": ("curl.exe -s https://api.ipify.org", "Get your public IP address"),
    "my ip": ("curl.exe -s https://api.ipify.org", "Get your public IP address"),
    "my ip address": ("curl.exe -s https://api.ipify.org", "Get your public IP address"),
    "show wifi password": ("PowerShell -Command \"(netsh wlan show profiles) | Select-String '\\:(.+)$' | ForEach { $name=$_.Matches.Groups[1].Value.Trim(); $_ } | ForEach { (netsh wlan show profile name=$name key=clear) } | Select-String 'Key Content\\W+\\:(.+)$' | ForEach { New-Object psobject -Property @{ PROFILE_NAME=$name; PASSWORD=$_.Matches.Groups[1].Value.Trim() } }\"", "Show saved WiFi passwords"),
    "wifi password": ("PowerShell -Command \"(netsh wlan show profiles) | Select-String '\\:(.+)$' | ForEach { $name=$_.Matches.Groups[1].Value.Trim(); $_ } | ForEach { (netsh wlan show profile name=$name key=clear) } | Select-String 'Key Content\\W+\\:(.+)$' | ForEach { New-Object psobject -Property @{ PROFILE_NAME=$name; PASSWORD=$_.Matches.Groups[1].Value.Trim() } }\"", "Show saved WiFi passwords"),
    "flush dns": ("ipconfig /flushdns", "Flush DNS cache"),
    "clear dns": ("ipconfig /flushdns", "Flush DNS cache"),
    "check disk": ("chkdsk", "Check disk for errors"),
}


# ═══════════════════════════════════════════════════════════
# File Type Extensions
# ═══════════════════════════════════════════════════════════

FILE_TYPE_MAP: dict[str, list[str]] = {
    "pdf": [".pdf"],
    "image": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"],
    "photo": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"],
    "video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"],
    "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"],
    "music": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"],
    "document": [".docx", ".doc", ".odt", ".rtf"],
    "spreadsheet": [".xlsx", ".xls", ".csv", ".ods"],
    "presentation": [".pptx", ".ppt", ".odp"],
    "text": [".txt", ".md", ".log"],
    "code": [".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs"],
    "python": [".py"],
    "javascript": [".js"],
    "html": [".html", ".htm"],
    "zip": [".zip", ".rar", ".7z", ".tar.gz", ".gz"],
    "archive": [".zip", ".rar", ".7z", ".tar.gz", ".gz"],
    "json": [".json"],
    "yaml": [".yaml", ".yml"],
    "xml": [".xml"],
}


# ═══════════════════════════════════════════════════════════
# Smart Open Engine
# ═══════════════════════════════════════════════════════════

class SmartOpenEngine:
    """
    Advanced intent router for "open", "launch", "navigate", and
    system action commands.

    Detection pipeline:
    1. System shortcuts (task manager, settings, etc.)
    2. Power commands (lock, restart, wifi password, etc.)
    3. App registry (chrome, vscode, spotify, etc.)
    4. URL detection (explicit URLs or site name inference)
    5. File type search ("latest pdf", "recent screenshot")
    6. Folder resolution (fuzzy search across common locations)
    7. File resolution (direct file open)
    """

    # Regex to detect "open" intent from natural language
    OPEN_INTENT = re.compile(
        r"^(?:open|launch|navigate\s+to|go\s+to|browse)\s+(.+)$",
        re.IGNORECASE,
    )

    # Sub-patterns for extracting targets
    _FOLDER_SUFFIX = re.compile(
        r"^(.+?)\s+(?:folder|directory|dir)$", re.IGNORECASE
    )
    _FILE_SUFFIX = re.compile(
        r"^(?:the\s+)?(?:file\s+)?(.+?)\s+(?:file)$", re.IGNORECASE
    )
    _IN_EXPLORER = re.compile(
        r"^(.+?)\s+in\s+(?:file\s+)?explorer$", re.IGNORECASE
    )
    _LATEST_FILE = re.compile(
        r"^(?:the\s+)?(?:latest|newest|most\s+recent|last)\s+(.+?)(?:\s+file)?$",
        re.IGNORECASE,
    )
    _URL_PATTERN = re.compile(
        r"^https?://", re.IGNORECASE
    )
    _RUN_AS_ADMIN = re.compile(
        r"^(.+?)\s+as\s+admin(?:istrator)?$", re.IGNORECASE
    )

    # Zip/compress patterns
    _ZIP_PATTERN = re.compile(
        r"^(?:create\s+(?:a\s+|an\s+)?zip\s+(?:folder\s+of\s+)?|zip\s+|compress\s+|archive\s+)(?:the\s+)?(?:folder\s+)?(.+?)(?:\s+(?:to|as|into)\s+(.+))?$",
        re.IGNORECASE,
    )
    _UNZIP_PATTERN = re.compile(
        r"^(?:unzip|extract|decompress)\s+(?:the\s+)?(?:file\s+)?(.+?)(?:\s+(?:to|into)\s+(.+))?$",
        re.IGNORECASE,
    )

    def __init__(self):
        self._is_windows = platform.system() == "Windows"
        self._home = Path.home()
        self._app_registry = WINDOWS_APP_REGISTRY if self._is_windows else LINUX_APP_REGISTRY
        # Debounce tracker — prevents opening multiple explorer windows in rapid succession
        self._last_explorer_path: str = ""
        self._last_explorer_time: float = 0.0
        self._EXPLORER_DEBOUNCE_S: float = 2.0  # seconds

    def try_resolve(self, user_input: str) -> OpenResult | None:
        """
        Try to resolve a natural language input into an open/launch command.
        Returns None if this doesn't look like an open intent.
        """
        user_input = user_input.strip()
        lower = user_input.lower()

        # Check GitHub clone intent first (no "open" prefix needed)
        clone_result = self._try_github_clone(lower, user_input)
        if clone_result:
            return clone_result

        # Check zip/compress first (doesn't need the "open" prefix)
        zip_result = self._try_zip_command(lower, user_input)
        if zip_result:
            return zip_result

        # Check power commands (some don't need "open" prefix)
        power = self._try_power_command(lower)
        if power:
            return power

        # Extract the target from "open X" / "launch X" etc.
        match = self.OPEN_INTENT.match(user_input)
        if not match:
            return None

        target = match.group(1).strip()
        target_lower = target.lower()

        # 1. "open X as admin"
        admin = self._RUN_AS_ADMIN.match(target)
        if admin and self._is_windows:
            inner = admin.group(1).strip()
            return OpenResult(
                command=f'PowerShell -Command "Start-Process {inner} -Verb RunAs"',
                explanation=f"Run {inner} as Administrator",
                target_type="power",
                confidence=0.90,
            )

        # 2. System shortcuts
        shortcut = self._try_system_shortcut(target_lower)
        if shortcut:
            return shortcut

        # 2.5 "current folder" / "this folder" / "here" / "."
        if target_lower in ("current folder", "this folder", "here", "current directory", "this directory", ".", ".."):
            return self._open_cwd()

        # 3. Explicit URL or site name
        url = self._try_url(target, target_lower)
        if url:
            return url

        # 4. Folder detection: "X folder" / "X directory"
        folder_match = self._FOLDER_SUFFIX.match(target)
        if folder_match:
            folder_name = folder_match.group(1).strip()
            return self._resolve_and_open_folder(folder_name)

        # 5. Check if target is a known folder name (current dir, home, well-known like downloads, desktop)
        folder_result = self._try_as_folder(target, target_lower)
        if folder_result:
            return folder_result

        # 6. "X in explorer"
        explorer_match = self._IN_EXPLORER.match(target)
        if explorer_match:
            folder_name = explorer_match.group(1).strip()
            return self._resolve_and_open_folder(folder_name)

        # 7. Check if target is an existing file
        if os.path.isfile(target):
            return self._open_file(target)

        # 8. "latest/newest <filetype>"
        latest = self._try_latest_file(target, target_lower)
        if latest:
            return latest

        # 9. "file X" pattern
        file_match = self._FILE_SUFFIX.match(target)
        if file_match:
            file_name = file_match.group(1).strip()
            return self._open_file(file_name)

        # 10. App registry & dynamic system app discovery
        app = self._try_app_registry(target_lower)
        if app:
            return app

        # 11. (Moved to 5.5 to prevent "current folder" being caught by 6)

        # 11.5 Nested folder detection ("open X inside Y")
        nested_match = re.search(r"(.+?)\s+(?:inside|in)\s+(.+)", target_lower)
        if nested_match:
            child = nested_match.group(1).replace(" folder", "").replace(" directory", "").strip()
            parent = nested_match.group(2).replace(" folder", "").replace(" directory", "").strip()

            # Find the parent folder first using the existing fuzzy finder
            parent_path = self._fuzzy_find_folder(parent)
            if parent_path:
                # Then fuzzy find the child ONLY within the parent path
                child_path = self._fuzzy_find_folder(child, search_root=parent_path)
                if child_path:
                    return self._open_folder(child_path, f"Open '{child}' inside '{parent}'")

        # 12. If nothing matched, try as a direct path
        if os.path.exists(target):
            if os.path.isdir(target):
                return self._open_folder(target, f"Open folder: {target}")
            else:
                return self._open_file(target)

        return None

    # ═══════════════════════════════════════════════════════
    # System Shortcuts
    # ═══════════════════════════════════════════════════════

    def _try_system_shortcut(self, target_lower: str) -> OpenResult | None:
        """Check against system shortcuts registry."""
        if not self._is_windows:
            return None
        if target_lower in SYSTEM_SHORTCUTS:
            cmd, name = SYSTEM_SHORTCUTS[target_lower]
            return OpenResult(
                command=cmd,
                explanation=f"Open {name}",
                target_type="system",
                confidence=0.95,
            )
        # Partial match
        for key, (cmd, name) in SYSTEM_SHORTCUTS.items():
            if key in target_lower or target_lower in key:
                return OpenResult(
                    command=cmd,
                    explanation=f"Open {name}",
                    target_type="system",
                    confidence=0.88,
                )
        return None

    # ═══════════════════════════════════════════════════════
    # Power Commands
    # ═══════════════════════════════════════════════════════

    def _try_power_command(self, lower: str) -> OpenResult | None:
        """Check against power commands (these can work without 'open' prefix)."""
        if not self._is_windows:
            return None
        if lower in POWER_COMMANDS:
            cmd, desc = POWER_COMMANDS[lower]
            return OpenResult(
                command=cmd,
                explanation=desc,
                target_type="power",
                confidence=0.95,
            )
        # Check with common prefixes stripped
        for prefix in ("open ", "launch ", "run ", "start ", "do ", "please "):
            stripped = lower.removeprefix(prefix)
            if stripped != lower and stripped in POWER_COMMANDS:
                cmd, desc = POWER_COMMANDS[stripped]
                return OpenResult(
                    command=cmd,
                    explanation=desc,
                    target_type="power",
                    confidence=0.93,
                )
        return None

    # ═══════════════════════════════════════════════════════
    # App Registry & Dynamic System Discovery
    # ═══════════════════════════════════════════════════════

    def _clean_app_name(self, target_lower: str) -> str:
        """Strip generic descriptors to isolate the application identifier."""
        return re.sub(
            r"\b(browser|brower|editor|ide|app|application|tool|program|software|client|viewer|utility)\b",
            "",
            target_lower,
            flags=re.IGNORECASE,
        ).strip()

    def _query_windows_app_paths(self, app_name: str) -> str | None:
        """Dynamically inspect Windows Registry App Paths (HKLM & HKCU)."""
        if not self._is_windows:
            return None
        try:
            import winreg
            keys_to_check = [
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            ]
            candidates = [app_name, f"{app_name}.exe"]
            for hkey, subkey in keys_to_check:
                try:
                    with winreg.OpenKey(hkey, subkey) as root_key:
                        num_subkeys = winreg.QueryInfoKey(root_key)[0]
                        for i in range(num_subkeys):
                            sk_name = winreg.EnumKey(root_key, i)
                            if any(sk_name.lower().startswith(c.lower()) for c in candidates):
                                with winreg.OpenKey(root_key, sk_name) as app_key:
                                    val, _ = winreg.QueryValueEx(app_key, "")
                                    if val and os.path.exists(val):
                                        return val
                except (OSError, PermissionError):
                    continue
        except (ImportError, Exception):
            pass
        return None

    def _try_app_registry(self, target_lower: str) -> OpenResult | None:
        """
        Dynamically resolves application launches:
        1. Built-in registry definitions
        2. Generic descriptor stripping (e.g. 'chrome browser' -> 'chrome')
        3. System PATH binary lookup
        4. Windows Registry App Paths discovery
        5. Zero-hardcoding dynamic process launcher
        """
        # 1. Exact match in registry
        if target_lower in self._app_registry:
            cmd, name = self._app_registry[target_lower]
            if cmd == "__EXPLORER_CWD__":
                result = self._open_cwd()
                return OpenResult(
                    command=result.command,
                    explanation=result.explanation,
                    target_type="app",
                    resolved_path=result.resolved_path,
                    confidence=result.confidence,
                )
            return OpenResult(
                command=cmd,
                explanation=f"Launch {name}",
                target_type="app",
                confidence=0.94,
            )

        # 2. Clean descriptors (browser, editor, app, etc.)
        stripped = self._clean_app_name(target_lower)
        if stripped and stripped in self._app_registry:
            cmd, name = self._app_registry[stripped]
            if cmd == "__EXPLORER_CWD__":
                result = self._open_cwd()
                return OpenResult(
                    command=result.command,
                    explanation=result.explanation,
                    target_type="app",
                    resolved_path=result.resolved_path,
                    confidence=result.confidence,
                )
            return OpenResult(
                command=cmd,
                explanation=f"Launch {name}",
                target_type="app",
                confidence=0.92,
            )

        # 3. Dynamic search: check if executable exists on PATH
        candidate = stripped or target_lower
        binary_path = shutil.which(candidate) or shutil.which(f"{candidate}.exe")
        if binary_path:
            cmd = (
                f'powershell -NoProfile -Command "Start-Process \'{candidate}\'"'
                if self._is_windows
                else f'"{binary_path}"'
            )
            return OpenResult(
                command=cmd,
                explanation=f"Launch {candidate.capitalize()} (found on PATH)",
                target_type="app",
                resolved_path=binary_path,
                confidence=0.94,
            )

        # 4. Windows App Paths Registry dynamic resolution
        if self._is_windows and candidate:
            reg_path = self._query_windows_app_paths(candidate)
            if reg_path:
                return OpenResult(
                    command=f'powershell -NoProfile -Command "Start-Process \'{reg_path}\'"',
                    explanation=f"Launch {candidate.capitalize()} (registered in Windows App Paths)",
                    target_type="app",
                    resolved_path=reg_path,
                    confidence=0.95,
                )

        # 5. Zero-Hardcoding Universal Fallback for single-token application names
        # E.g. 'open cursor', 'open brave', 'open obsidian', 'open blender'
        if candidate and re.match(r"^[a-zA-Z0-9_\-\.]+$", candidate):
            if self._is_windows:
                cmd = f'powershell -NoProfile -Command "Start-Process \'{candidate}\'"'
            elif platform.system() == "Darwin":
                cmd = f'open -a "{candidate}"'
            else:
                cmd = f'xdg-open "{candidate}"'

            return OpenResult(
                command=cmd,
                explanation=f"Launch {candidate.capitalize()} via system process manager",
                target_type="app",
                confidence=0.89,
            )

        return None

    # ═══════════════════════════════════════════════════════
    # URL Resolution
    # ═══════════════════════════════════════════════════════

    def _try_url(self, target: str, target_lower: str) -> OpenResult | None:
        """Resolve explicit URLs or infer from site names."""
        # Explicit URL
        if self._URL_PATTERN.match(target):
            cmd = self._url_open_cmd(target)
            return OpenResult(
                command=cmd,
                explanation=f"Open URL: {target}",
                target_type="url",
                confidence=0.95,
            )

        # Dynamic GitHub profile and repositories resolution
        if target_lower in ("github profile", "my github profile", "mine github profile", "my github", "mine github", "my profile on github"):
            try:
                from operations.github_access import get_cached_github_identity
                gh_id = get_cached_github_identity()
                url = gh_id.profile_url or "https://github.com"
                cmd = self._url_open_cmd(url)
                username_label = f" for @{gh_id.username}" if gh_id.username else ""
                return OpenResult(
                    command=cmd,
                    explanation=f"Open GitHub profile{username_label} in default browser",
                    target_type="url",
                    confidence=0.98,
                    alternatives=["gh browse"] if gh_id.cli_installed else [],
                )
            except Exception:
                pass

        if target_lower in ("github repos", "my github repos", "mine github repos", "my repos", "mine repos", "github repositories", "my repositories"):
            try:
                from operations.github_access import get_cached_github_identity
                gh_id = get_cached_github_identity()
                if gh_id.cli_installed:
                    return OpenResult(
                        command="gh repo list --limit 15",
                        explanation=f"List repositories for @{gh_id.username or 'authenticated user'} using GitHub CLI",
                        target_type="cli",
                        confidence=0.98,
                        alternatives=[self._url_open_cmd(f"{gh_id.profile_url}?tab=repositories")] if gh_id.profile_url else [],
                    )
                elif gh_id.profile_url:
                    url = f"{gh_id.profile_url}?tab=repositories"
                    return OpenResult(
                        command=self._url_open_cmd(url),
                        explanation=f"Open GitHub repositories for @{gh_id.username}: {url}",
                        target_type="url",
                        confidence=0.95,
                        alternatives=[gh_id.install_command],
                    )
            except Exception:
                pass

        if target_lower in ("install github cli", "install gh", "install gh cli", "install github"):
            try:
                from operations.github_access import get_github_install_command
                inst_cmd = get_github_install_command()
                return OpenResult(
                    command=inst_cmd,
                    explanation="Install GitHub CLI (gh) via system package manager",
                    target_type="cli",
                    confidence=0.98,
                )
            except Exception:
                pass

        # Site name inference
        if target_lower in SITE_MAP:
            url = SITE_MAP[target_lower]
            cmd = self._url_open_cmd(url)
            return OpenResult(
                command=cmd,
                explanation=f"Open {target} ({url})",
                target_type="url",
                confidence=0.92,
                alternatives=[url],
            )

        # Domain / Port / Path pattern (e.g. google.com, localhost:3000, huggingface.co/models)
        if re.match(r"^(?:localhost:\d+|[\w.-]+\.[a-zA-Z]{2,}(?:/\S*)?)$", target):
            scheme = "http" if target.startswith("localhost") else "https"
            url = f"{scheme}://{target}"
            cmd = self._url_open_cmd(url)
            return OpenResult(
                command=cmd,
                explanation=f"Open website: {url}",
                target_type="url",
                confidence=0.90,
            )

        return None

    def _url_open_cmd(self, url: str) -> str:
        """Generate platform-specific URL open command.

        Uses powershell Start-Process on Windows (works from any shell context,
        unlike 'cmd /c start' which fails when the active shell is PowerShell).
        """
        if self._is_windows:
            # Escape single quotes in URL for PowerShell
            safe_url = url.replace("'", "''")
            return f"powershell -NoProfile -Command \"Start-Process '{safe_url}'\""
        elif platform.system() == "Darwin":
            return f'open "{url}"'
        else:
            return f'xdg-open "{url}"'

    # ═══════════════════════════════════════════════════════
    # Latest File Finder
    # ═══════════════════════════════════════════════════════

    def _try_latest_file(self, target: str, target_lower: str) -> OpenResult | None:
        """Find the most recently modified file of a given type."""
        match = self._LATEST_FILE.match(target)
        if not match:
            return None

        file_type = match.group(1).strip().lower()
        extensions = FILE_TYPE_MAP.get(file_type)
        if not extensions:
            # Try the raw extension
            ext = f".{file_type}"
            extensions = [ext]

        # Search common locations
        search_dirs = [
            os.getcwd(),
            str(self._home / "Desktop"),
            str(self._home / "Downloads"),
            str(self._home / "Documents"),
        ]

        best_file = None
        best_mtime = 0

        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue
            try:
                for entry in os.scandir(search_dir):
                    if not entry.is_file():
                        continue
                    if any(entry.name.lower().endswith(ext) for ext in extensions):
                        try:
                            mtime = entry.stat().st_mtime
                            if mtime > best_mtime:
                                best_mtime = mtime
                                best_file = entry.path
                        except OSError:
                            pass
            except OSError:
                continue

        if best_file is not None:
            return self._open_file(str(best_file), explanation=f"Open latest {file_type}: {os.path.basename(best_file)}")

        return None

    # ═══════════════════════════════════════════════════════
    # Folder Resolution
    # ═══════════════════════════════════════════════════════

    def _resolve_and_open_folder(self, name: str) -> OpenResult:
        """Resolve a folder name to a path and generate open command."""
        resolved = self._resolve_folder(name)
        if resolved:
            return self._open_folder(resolved, f"Open folder: {os.path.basename(resolved)}")

        # Couldn't find — still generate a best-effort command
        return OpenResult(
            command=f'explorer "{name}"' if self._is_windows else f'xdg-open "{name}"',
            explanation=f"Open folder: {name} (path not verified)",
            target_type="folder",
            confidence=0.60,
        )

    def _resolve_folder(self, name: str) -> str | None:
        """
        Resolve a folder name to an absolute path.

        Search order:
        1. Exact path (if absolute or relative and exists)
        2. Subfolder of current directory (case-insensitive)
        3. Well-known directories (Desktop, Documents, Downloads, etc.)
        4. Home directory children
        5. Drive roots (Windows only)
        """
        # Exact path check
        if os.path.isdir(name):
            return os.path.abspath(name)

        name_lower = name.lower().strip()

        # Well-known folder names
        WELL_KNOWN = {
            "desktop": self._home / "Desktop",
            "documents": self._home / "Documents",
            "my documents": self._home / "Documents",
            "downloads": self._home / "Downloads",
            "pictures": self._home / "Pictures",
            "music": self._home / "Music",
            "videos": self._home / "Videos",
            "appdata": self._home / "AppData",
            "home": self._home,
            "user": self._home,
            "temp": Path(os.environ.get("TEMP", "/tmp")),
            "tmp": Path(os.environ.get("TEMP", "/tmp")),
        }

        if name_lower in WELL_KNOWN:
            # Well-known folders are deterministic per-user locations — return
            # the canonical path even when it does not exist yet (fresh
            # profiles, headless servers, CI). The OS opener will create or
            # surface a clear error, which beats a low-confidence guess.
            return str(WELL_KNOWN[name_lower])

        # Search current directory (case-insensitive)
        cwd = os.getcwd()
        result = self._search_dir_for(cwd, name_lower)
        if result:
            return result

        # Search home directory children
        result = self._search_dir_for(str(self._home), name_lower)
        if result:
            return result

        # Search Desktop
        desktop = str(self._home / "Desktop")
        if os.path.isdir(desktop):
            result = self._search_dir_for(desktop, name_lower)
            if result:
                return result

        # Search Documents
        docs = str(self._home / "Documents")
        if os.path.isdir(docs):
            result = self._search_dir_for(docs, name_lower)
            if result:
                return result

        # Search Downloads
        downloads = str(self._home / "Downloads")
        if os.path.isdir(downloads):
            result = self._search_dir_for(downloads, name_lower)
            if result:
                return result

        # Windows: search drive roots
        if self._is_windows:
            for drive_letter in "CDEFGH":
                drive_root = f"{drive_letter}:\\"
                if os.path.isdir(drive_root):
                    result = self._search_dir_for(drive_root, name_lower)
                    if result:
                        return result

        return None

    def _search_dir_for(self, directory: str, name_lower: str) -> str | None:
        """Search a directory for a folder with case-insensitive name matching."""
        try:
            for entry in os.scandir(directory):
                if entry.is_dir() and entry.name.lower() == name_lower:
                    return entry.path
        except (OSError, PermissionError):
            pass

        # Partial / fuzzy match (name contains the search term)
        # Skip hidden/dotfile folders to avoid e.g. '.ira' matching 'ira'
        try:
            for entry in os.scandir(directory):
                if not entry.is_dir():
                    continue
                entry_lower = entry.name.lower()
                # Skip hidden/dotfile dirs
                if entry_lower.startswith("."):
                    continue
                if name_lower in entry_lower:
                    return entry.path
        except (OSError, PermissionError):
            pass

        return None

    def _fuzzy_find_folder(self, name_lower: str, search_root: str | None = None) -> str | None:
        """Last-resort fuzzy search across multiple locations, or a specific root."""
        best_match = None
        best_score = 0

        if search_root:
            # Recursive search inside a specific root with a depth limit
            try:
                # os.walk yields (dirpath, dirnames, filenames)
                for root, dirs, _ in os.walk(search_root):
                    # Limit depth to 3 to prevent hanging
                    depth = root[len(search_root):].count(os.sep)
                    if depth > 3:
                        dirs.clear() # Stop descending further
                        continue

                    for d in dirs:
                        if d.startswith("."):
                            continue
                        score = SmartOpenEngine._similarity_score(name_lower, d.lower())
                        if score > best_score and score > 0.5:
                            best_score = score
                            best_match = os.path.join(root, d)
            except (OSError, PermissionError):
                pass
            return best_match

        search_locations = [
            os.getcwd(),
            str(self._home),
            str(self._home / "Desktop"),
            str(self._home / "Documents"),
            str(self._home / "Downloads"),
        ]

        for loc in search_locations:
            if not os.path.isdir(loc):
                continue
            try:
                for entry in os.scandir(loc):
                    if not entry.is_dir():
                        continue
                    entry_lower = entry.name.lower()
                    # Calculate simple similarity score
                    score = SmartOpenEngine._similarity_score(name_lower, entry_lower)
                    if score > best_score and score > 0.5:
                        best_score = score
                        best_match = entry.path
            except (OSError, PermissionError):
                continue

        return best_match

    @staticmethod
    def _similarity_score(a: str, b: str) -> float:
        """Simple similarity scoring (0.0 to 1.0)."""
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.8
        # Character overlap ratio
        common = sum(1 for c in a if c in b)
        max_len = max(len(a), len(b))
        if max_len == 0:
            return 0.0
        return common / max_len

    def _try_as_folder(self, target: str, target_lower: str) -> OpenResult | None:
        """Check if the target is a folder (well-known or in current directory)."""
        resolved = self._resolve_folder(target)
        if resolved:
            return self._open_folder(resolved, f"Open folder: {os.path.basename(resolved)}")
        return None

    # ═══════════════════════════════════════════════════════
    # Command Generators
    # ═══════════════════════════════════════════════════════

    def _open_folder(self, path: str, explanation: str = "") -> OpenResult:
        """Generate platform-specific folder open command with dedup guard.

        Prevents multiple explorer windows from opening when the user re-runs
        the same "open file explorer" command within EXPLORER_DEBOUNCE_S seconds.
        """
        import time as _time
        abs_path = os.path.abspath(path)

        # Debounce: if same path was just opened, don't spawn another window
        now = _time.time()
        if (
            self._is_windows
            and abs_path == self._last_explorer_path
            and (now - self._last_explorer_time) < self._EXPLORER_DEBOUNCE_S
        ):
            return OpenResult(
                command="echo Already open",
                explanation=f"File Explorer already open at: {abs_path}",
                target_type="folder",
                resolved_path=abs_path,
                confidence=0.99,
            )

        if self._is_windows:
            cmd = f'explorer "{abs_path}"'
            self._last_explorer_path = abs_path
            self._last_explorer_time = now
        elif platform.system() == "Darwin":
            cmd = f'open "{abs_path}"'
        else:
            cmd = f'xdg-open "{abs_path}"'

        return OpenResult(
            command=cmd,
            explanation=explanation or f"Open folder: {abs_path}",
            target_type="folder",
            resolved_path=abs_path,
            confidence=0.93,
        )

    def _open_cwd(self) -> OpenResult:
        """Open current working directory in file explorer (dedup-safe)."""
        cwd = os.getcwd()
        return self._open_folder(cwd, "Open current directory in File Explorer")

    def _open_file(self, path: str, explanation: str = "") -> OpenResult:
        """Generate platform-specific file open command."""
        abs_path = os.path.abspath(path)
        if self._is_windows:
            # Use powershell Start-Process to avoid cmd /c start shell confusion
            safe_path = abs_path.replace("'", "''")
            cmd = f"powershell -NoProfile -Command \"Start-Process '{safe_path}'\""
        elif platform.system() == "Darwin":
            cmd = f'open "{abs_path}"'
        else:
            cmd = f'xdg-open "{abs_path}"'

        return OpenResult(
            command=cmd,
            explanation=explanation or f"Open file: {os.path.basename(abs_path)}",
            target_type="file",
            resolved_path=abs_path,
            confidence=0.92,
        )

    # ═══════════════════════════════════════════════════════
    # Zip / Compress Commands
    # ═══════════════════════════════════════════════════════

    def _try_zip_command(self, lower: str, original: str) -> OpenResult | None:
        """Handle zip/compress and unzip/extract commands."""
        if not self._is_windows:
            return None

        zip_match = self._ZIP_PATTERN.match(lower)
        if zip_match:
            source = zip_match.group(1).strip()
            dest = zip_match.group(2)
            # Clean up trailing 'folder' or 'directory'
            source = re.sub(r'\s+(?:folder|directory|dir)$', '', source, flags=re.IGNORECASE)

            actual_source = source
            if not os.path.exists(source):
                fuzzy = self._fuzzy_find_folder(source)
                if fuzzy:
                    actual_source = fuzzy

            if not dest:
                # Use base name if resolved, else the raw string
                base_name = os.path.basename(actual_source.rstrip("\\/")) if actual_source != source else source
                dest = f"{base_name}.zip"
            dest = dest.strip()
            cmd = f'PowerShell -Command "Compress-Archive -Path \'{actual_source}\' -DestinationPath \'{dest}\' -Force"'
            return OpenResult(
                command=cmd,
                explanation=f"Compress '{actual_source}' → '{dest}'",
                target_type="power",
                confidence=0.90,
            )

        unzip_match = self._UNZIP_PATTERN.match(lower)
        if unzip_match:
            source = unzip_match.group(1).strip()
            # If source contains a web URL or web scrape keywords, skip zip archive handling
            if "http://" in source or "https://" in source or re.search(r"\b(tables?|links?|data|web|website|site)\b", source, re.IGNORECASE):
                return None
            dest = unzip_match.group(2)

            # Fuzzy resolve the source archive using folder fuzzy finding logic if missing
            actual_source = source
            if not os.path.exists(source):
                # Search across paths specifically for this file
                # If we had a fuzzy file finder we would use it, but checking common roots is easy:
                search_roots = [
                    os.getcwd(), str(self._home / "Downloads"), str(self._home / "Desktop")
                ]
                for root in search_roots:
                    try:
                        for entry in os.scandir(root):
                            if not entry.is_dir() and source in entry.name.lower():
                                actual_source = entry.path
                                break
                    except (OSError, PermissionError):
                        continue

            if not dest:
                dest = "."
            dest = dest.strip()
            cmd = f'PowerShell -Command "Expand-Archive -Path \'{actual_source}\' -DestinationPath \'{dest}\' -Force"'
            return OpenResult(
                command=cmd,
                explanation=f"Extract '{actual_source}' → '{dest}'",
                target_type="power",
                confidence=0.90,
            )

        return None

    # ═══════════════════════════════════════════════════════
    # GitHub Clone Intent
    # ═══════════════════════════════════════════════════════

    # Patterns that signal a clone/download intent
    _CLONE_PATTERN = re.compile(
        r"^(?:clone|download|get)\s+"
        r"(?:github\s+repo\s+|github\s+repository\s+|repo\s+)?"
        r"(.+)$",
        re.IGNORECASE,
    )
    # Looks like owner/repo (no spaces, contains a /)
    _OWNER_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
    # Full URL
    _FULL_URL = re.compile(r"^https?://")

    def _try_github_clone(self, lower: str, original: str) -> OpenResult | None:
        """
        Detect GitHub clone intents and generate the appropriate git clone command.

        Supported forms:
          clone github repo <name>      → search GitHub API, clone top result
          clone <owner>/<repo>          → git clone https://github.com/owner/repo.git
          clone <https://...>           → git clone <url>
          clone <bare-name>             → search GitHub API for top starred match
        """
        m = self._CLONE_PATTERN.match(original.strip())
        if not m:
            return None

        target = m.group(1).strip()

        # ── Case 1: Full URL ──────────────────────────────────────
        if self._FULL_URL.match(target):
            return OpenResult(
                command=f"git clone {target}",
                explanation=f"Clone repository: {target}",
                target_type="git",
                confidence=0.97,
            )

        # ── Case 2: owner/repo shorthand ──────────────────────────
        if self._OWNER_REPO.match(target):
            url = f"https://github.com/{target}.git"
            return OpenResult(
                command=f"git clone {url}",
                explanation=f"Clone GitHub repo: {target}",
                target_type="git",
                confidence=0.96,
            )

        # ── Case 3: Bare name — search GitHub API ────────────────
        result = self._github_api_search(target)
        if result:
            full_name, clone_url, stars, description = result
            return OpenResult(
                command=f"git clone {clone_url}",
                explanation=(
                    f"Clone '{full_name}' (★ {stars:,}) — {description[:80] if description else 'No description'}"
                ),
                target_type="git",
                confidence=0.88,
            )

        # Fallback: best-effort clone by name
        return OpenResult(
            command=f"git clone https://github.com/{target}",
            explanation=f"Clone GitHub repo (best-effort): {target}",
            target_type="git",
            confidence=0.60,
        )

    def _github_api_search(self, query: str) -> tuple | None:
        """
        Search GitHub's public API for the most popular repo matching `query`.
        Returns (full_name, clone_url, stars, description) or None.
        Requires no auth for public repos (60 req/hour rate limit).
        """
        try:
            import json as _json
            import urllib.parse
            import urllib.request

            q = urllib.parse.quote(query)
            url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=1"
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "NeuroShell/4.2",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read().decode())

            items = data.get("items", [])
            if not items:
                return None

            top = items[0]
            return (
                top.get("full_name", query),
                top.get("clone_url", f"https://github.com/{query}.git"),
                top.get("stargazers_count", 0),
                top.get("description") or "",
            )
        except Exception:
            # Network unavailable, rate-limited, etc. — fail silently
            return None


import asyncio
import subprocess
from collections.abc import AsyncGenerator
from typing import Any

try:
    from intelligence.tools.base_tool import BaseTool
except ImportError:
    class BaseTool:
        pass

class SmartOpenTool(BaseTool):
    """
    Agentic interface for resolving and executing open/launch intents.
    Conforms to the BaseTool streaming protocol.
    """
    @property
    def name(self) -> str:
        return "smart_open_tool"

    @property
    def description(self) -> str:
        return "Resolve and execute natural language open/launch commands (e.g. 'open chrome', 'launch vscode')."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The natural language instruction (e.g. 'open youtube')."}
            },
            "required": ["query"]
        }

    async def call(self, **kwargs) -> AsyncGenerator[dict[str, Any], None]:
        query = kwargs.get("query")
        if not query:
            yield {"type": "error", "message": "query parameter is required"}
            return

        yield {"type": "progress", "message": f"Resolving open intent for '{query}'..."}

        loop = asyncio.get_running_loop()
        engine = SmartOpenEngine()

        def _resolve_and_execute():
            result = engine.try_resolve(query)
            if not result:
                return None

            # Fire and forget the command
            try:
                import sys
                if sys.platform == "win32":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 0
                    cmd_args = ["cmd.exe", "/c", result.command]
                    subprocess.Popen(
                        cmd_args,
                        shell=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        startupinfo=si,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        start_new_session=True,
                    )
                else:
                    subprocess.Popen(
                        ["sh", "-c", result.command],
                        shell=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                return result
            except Exception as e:
                raise RuntimeError(f"Failed to launch {result.command}: {e}")

        try:
            res = await loop.run_in_executor(None, _resolve_and_execute)
            if res is None:
                yield {"type": "result", "data": f"Could not resolve open intent for '{query}'"}
            else:
                yield {"type": "result", "data": f"Launched: {res.explanation} (target_type: {res.target_type})"}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
