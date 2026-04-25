# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell NL → Command Translator — Production Grade
Multi-step translation with disambiguation, context-aware prompt building,
confidence calibration, learn-from-feedback integration, and
advanced smart-open resolution (folders, apps, URLs, system shortcuts).
"""

import time
import json
import re
import os
import shlex
import subprocess
from typing import Any, Callable, Optional
from dataclasses import dataclass, field

from observability.provenance import ProvenanceTag, ProvenanceSource  # type: ignore
from intelligence.sanitizer import LLMSanitizer  # type: ignore


# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class TranslationStep:
    """A single step in a multi-step translation."""
    command: str
    explanation: str
    is_destructive: bool = False
    order: int = 0
    depends_on: list[int] = field(default_factory=list)
    condition: str = ""    # "on_success", "on_failure", "always"


@dataclass
class TranslationResult:
    """Comprehensive translation result."""
    command: str
    confidence: float
    explanation: str
    is_destructive: bool = False
    alternatives: list[str] = field(default_factory=list)
    provenance: Optional[ProvenanceTag] = None
    steps: list[TranslationStep] = field(default_factory=list)
    is_multi_step: bool = False
    disambiguation: list[dict] = field(default_factory=list)
    needs_disambiguation: bool = False
    source: str = "llm"

    @property
    def has_command(self) -> bool:
        return bool(self.command)

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.8


# ═══════════════════════════════════════════════════════════
# Common Command Patterns (for fast local translation)
# ═══════════════════════════════════════════════════════════

def _get_telemetry_cmd(arg: str) -> str:
    import sys
    import os
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller places the intelligence folder inside _internal
        script_path = os.path.join(sys._MEIPASS, "intelligence", "ui_telemetry.py")
    else:
        script_path = "intelligence/ui_telemetry.py"
    return f'python "{script_path}" {arg}'


LOCAL_PATTERNS = {
    # ═══════════════════════════════════════════════════════════
    # Cockpit UI Mission Commands
    # ═══════════════════════════════════════════════════════════
    r"show dashboard": _get_telemetry_cmd("dashboard"),
    r"monitor performance": _get_telemetry_cmd("performance"),
    r"search system": _get_telemetry_cmd("search"),
    r"toggle theme": _get_telemetry_cmd("theme"),
    r"run safety check": _get_telemetry_cmd("safety"),
    r"deploy status": _get_telemetry_cmd("deploy"),
    r"start beginner guide": _get_telemetry_cmd("guide"),
    r"show deployment graph": _get_telemetry_cmd("graph"),
    r"deploy now": _get_telemetry_cmd("deploy_now"),
    r"help": _get_telemetry_cmd("help"),

    # File operations
    r"(?:show|list|view)\s+(?:all\s+)?files?(?:\s+in\s+(.+))?": "ls {0}",
    r"(?:make|create)\s+(?:a\s+)?(?:directory|folder|dir)\s+(?:called\s+)?(\S+)": "mkdir {0}",
    r"(?:delete|remove)\s+(?:the\s+)?(?:file|directory|folder)\s+(\S+)": "rm {0}",
    r"(?:copy|cp)\s+(\S+)\s+(?:to\s+)?(\S+)": "cp {0} {1}",
    r"(?:move|mv|rename)\s+(\S+)\s+(?:to\s+)?(\S+)": "mv {0} {1}",
    r"(?:show|display|cat|view)\s+(?:the\s+)?(?:contents?\s+of\s+)?(\S+)": "cat {0}",
    r"(?:find|search|locate)\s+(?:files?\s+)?(?:named?\s+)?(\S+)": "find . -name '*{0}*'",
    r"(?:count|how many)\s+(?:lines?\s+in)\s+(\S+)": "wc -l {0}",
    r"(?:show|what(?:'s| is))\s+(?:the\s+)?(?:current\s+)?(?:directory|dir|pwd)": "pwd",
    r"(?:go|change|cd|switch)\s+(?:to\s+)?(?:directory\s+)?(\S+)": "cd {0}",
    r"(?:show|view)\s+(?:the\s+)?(?:size|sizes)\s+(?:of\s+)?(?:all\s+)?(?:files?|folders?|directories)": "du -sh *",
    r"(?:compress|zip)\s+(\S+)": "zip -r {0}.zip {0}",
    r"(?:extract|unzip)\s+(\S+)": "unzip {0}",
    r"(?:compare|diff)\s+(\S+)\s+(?:and|with|vs)\s+(\S+)": "diff {0} {1}",
    r"(?:find|search)\s+(?:for\s+)?['\"](.+?)['\"]\s+in\s+(\S+)": "grep -r '{0}' {1}",
    r"(?:search|grep|find)\s+(?:for\s+)?['\"](.+?)['\"]\s+(?:in\s+)?(?:all\s+)?files?": "grep -r '{0}' .",

    # Git operations
    r"(?:what(?:'s| is)|show|check)\s+(?:the\s+)?git\s+status": "git status",
    r"(?:show|list)\s+(?:all\s+)?(?:git\s+)?branches": "git branch -a",
    r"(?:create|make)\s+(?:a\s+)?(?:new\s+)?branch\s+(?:called\s+)?(\S+)": "git checkout -b {0}",
    r"(?:switch|checkout)\s+(?:to\s+)?(?:branch\s+)?(\S+)": "git checkout {0}",
    r"(?:commit|save)\s+(?:with\s+)?(?:message\s+)?['\"](.+)['\"]": 'git commit -m "{0}"',
    r"(?:push|upload)\s+(?:to\s+)?(?:remote)?": "git push",
    r"(?:git\s+)?(?:pull|fetch)(?:\s+(?:from\s+)?(?:remote|origin))?": "git pull",
    r"(?:update|sync)\s+(?:git\s+)?(?:repo(?:sitory)?|branch|code)(?:\s+from\s+(?:remote|origin))?": "git pull",
    r"(?:show|view)\s+(?:recent\s+)?(?:git\s+)?(?:log|history)": "git log --oneline -10",
    r"(?:stash|save)\s+(?:my\s+)?changes": "git stash",
    r"(?:add|stage)\s+all\s+(?:files?|changes)": "git add -A",
    r"(?:add|stage)\s+(\S+)": "git add {0}",
    r"(?:undo|revert)\s+(?:last\s+)?commit": "git reset --soft HEAD~1",
    r"(?:show|view)\s+(?:git\s+)?diff": "git diff",
    # Git clone — explicit URL or owner/repo falls here; bare-name goes to smart_open
    r"(?:clone|git clone)\s+(https?://\S+)": "git clone {0}",
    r"(?:clone|git clone)\s+([\w.-]+/[\w.-]+)": "git clone https://github.com/{0}.git",
    r"(?:clone)\s+(\S+)": "git clone {0}",
    r"(?:delete|remove)\s+branch\s+(\S+)": "git branch -d {0}",
    r"(?:merge)\s+(?:branch\s+)?(\S+)": "git merge {0}",
    r"(?:show|list)\s+(?:git\s+)?(?:remote|remotes)": "git remote -v",
    r"(?:show|list)\s+(?:git\s+)?tags?": "git tag",

    # System operations
    r"(?:show|what)\s+(?:is\s+)?(?:free\s+)?(?:disk\s+)?space": "df -h",
    r"(?:show|what)\s+(?:is\s+)?memory\s+usage": "free -h",
    r"(?:who\s+am\s+i|current\s+user)": "whoami",
    r"(?:what(?:'s| is)|show)\s+(?:the\s+)?(?:system\s+)?(?:date|time)": "date",
    r"(?:show|list)\s+(?:running\s+)?processes": "ps aux",
    r"(?:kill|stop)\s+process\s+(\d+)": "kill {0}",
    r"(?:find|show)\s+(?:my\s+)?(?:ip|IP)\s+(?:address)?": "ip addr show",
    r"(?:check|test)\s+(?:internet|network)\s+(?:connection)?": "ping -c 4 8.8.8.8",
    r"(?:show|what)\s+(?:is\s+)?(?:system\s+)?uptime": "uptime",
    r"(?:show|list)\s+(?:all\s+)?environment\s+variables?": "env",
    r"(?:clear|cls)\s+(?:the\s+)?(?:screen|terminal|console)": "clear",
    r"(?:show|what)\s+(?:is\s+)?(?:my\s+)?hostname": "hostname",
    r"(?:restart|reboot)\s+(?:the\s+)?(?:computer|system|pc|machine)": "shutdown -r",
    r"(?:shutdown|turn off|power off)\s+(?:the\s+)?(?:computer|system|pc|machine)": "shutdown -s",

    # Package management
    r"install\s+(?:package\s+)?(\S+)(?:\s+(?:with|using)\s+pip)?": "pip install {0}",
    r"uninstall\s+(?:package\s+)?(\S+)": "pip uninstall {0}",
    r"(?:list|show)\s+(?:installed\s+)?(?:pip\s+)?packages": "pip list",
    r"(?:update|upgrade)\s+pip": "pip install --upgrade pip",
    r"(?:install|add)\s+(\S+)\s+(?:with|using)\s+npm": "npm install {0}",
    r"npm\s+install\s+(\S+)": "npm install {0}",
    r"(?:list|show)\s+npm\s+packages": "npm list",
    r"(?:run|start)\s+(?:npm\s+)?(?:dev|development)\s+(?:server)?": "npm run dev",
    r"(?:create|init)\s+(?:a\s+)?(?:new\s+)?(?:node|npm)\s+project": "npm init -y",
    r"(?:create|init)\s+(?:a\s+)?(?:new\s+)?(?:python|pip)\s+(?:virtual\s+)?(?:env|environment|venv)": "python -m venv .venv",
    r"(?:activate)\s+(?:the\s+)?(?:virtual\s+)?(?:env|environment|venv)": ".venv\\Scripts\\activate",

    # Docker
    r"(?:list|show)\s+(?:running\s+)?(?:docker\s+)?containers?": "docker ps",
    r"(?:list|show)\s+(?:all\s+)?(?:docker\s+)?images?": "docker images",
    r"(?:stop|halt)\s+(?:docker\s+)?container\s+(\S+)": "docker stop {0}",
    r"(?:start|run)\s+(?:docker\s+)?container\s+(\S+)": "docker start {0}",
    r"(?:remove|delete)\s+(?:docker\s+)?container\s+(\S+)": "docker rm {0}",
    r"(?:remove|delete)\s+(?:docker\s+)?image\s+(\S+)": "docker rmi {0}",
    r"(?:show|view)\s+(?:docker\s+)?logs?\s+(?:for\s+)?(\S+)": "docker logs {0}",
    r"docker\s+compose\s+up": "docker compose up -d",

    # Python operations
    r"run\s+python\s+(?:script\s+)?(\S+)": "python {0}",
    r"run\s+(?:the\s+)?(?:tests?|pytest)": "python -m pytest",
    r"(?:check|show)\s+python\s+version": "python --version",
    r"(?:run|start)\s+(?:flask|django)\s+(?:server|app)": "python -m flask run",
    r"(?:format|lint)\s+(?:the\s+)?(?:code|python)": "python -m black .",
    r"(?:freeze|export)\s+(?:pip\s+)?(?:requirements|deps|dependencies)": "pip freeze > requirements.txt",
    r"install\s+(?:from\s+)?requirements": "pip install -r requirements.txt",

    # Network
    r"(?:ping)\s+(\S+)": "ping {0}",
    r"(?:trace(?:route)?|tracert)\s+(\S+)": "traceroute {0}",
    r"(?:lookup|resolve|nslookup)\s+(?:dns\s+)?(?:for\s+)?(\S+)": "nslookup {0}",
    r"(?:show|list)\s+(?:open\s+)?(?:network\s+)?ports": "netstat -tulpn",
    r"(?:download|fetch|wget|curl)\s+(\S+)": "curl -O {0}",
    r"(?:check|test)\s+(?:if\s+)?(?:port\s+)?(\d+)\s+(?:is\s+)?(?:open|listening)": "netstat -an | grep {0}",

    # Miscellaneous
    r"(?:show|view)\s+(?:system\s+)?(?:info|information)": "uname -a",
    r"(?:what|which)\s+(?:shell|terminal)\s+(?:am i using|is this)": "echo $SHELL",
    r"(?:make|set)\s+(\S+)\s+(?:executable|runnable)": "chmod +x {0}",
    r"(?:show|what)\s+(?:is\s+)?(?:the\s+)?(?:weather)": "curl wttr.in",
}

# Windows-specific pattern overrides
WINDOWS_OVERRIDES = {
    # File operations
    r"(?:show|list|view)\s+(?:all\s+)?files?": "dir",
    r"(?:deep\s+)?(?:find|search|locate)\s+(?:for\s+)?(?:files?\s+)?(?:named?\s+)?(.+)": 'python intelligence/deep_search.py "{0}"',
    r"(?:deep\s+)?(?:search|grep|find)\s+(?:for\s+)?['\"](.+?)['\"]\s+(?:in\s+)?(?:all\s+)?files?": 'findstr /s /i "{0}" *',
    r"(?:deep\s+)?(?:search|find)\s+(?:in\s+)?(?:explorer|file explorer|windows)\s+(?:for\s+)?(.+)": 'explorer "search-ms:query={0}"',
    r"(?:deep\s+)?(?:search|grep|find)\s+(?:for\s+)?(.+?)\s+(?:in\s+)?(?:explorer|file explorer|windows)": 'explorer "search-ms:query={0}"',
    r"(?:show|view)\s+(?:the\s+)?(?:size|sizes)\s+(?:of\s+)?(?:all\s+)?(?:files?|folders?|directories)": "dir /s",
    r"(?:compare|diff)\s+(\S+)\s+(?:and|with|vs)\s+(\S+)": "fc {0} {1}",
    r"(?:clear|cls)\s+(?:the\s+)?(?:screen|terminal|console)": "cls",

    # System
    r"(?:show|what)\s+(?:is\s+)?(?:free\s+)?(?:disk\s+)?space": "wmic logicaldisk get size,freespace,caption",
    r"(?:show|what)\s+(?:is\s+)?memory\s+usage": "systeminfo | findstr Memory",
    r"(?:find|show)\s+(?:my\s+)?(?:ip|IP)\s+(?:address)?": "ipconfig",
    r"(?:check|test)\s+(?:internet|network)\s+(?:connection)?": "ping -n 4 8.8.8.8",
    r"(?:show|list)\s+(?:running\s+)?processes": "tasklist",
    r"(?:kill|stop)\s+process\s+(\d+)": "taskkill /PID {0} /F",
    r"(?:show|list)\s+(?:all\s+)?environment\s+variables?": "set",
    r"(?:update|upgrade)\s+windows(?:\s+system)?": "winget upgrade --all",
    r"(?:show|view)\s+(?:system\s+)?(?:info|information)": "systeminfo",
    r"(?:restart|reboot)\s+(?:the\s+)?(?:computer|system|pc|machine)": "shutdown /r /t 5",
    r"(?:shutdown|turn off|power off)\s+(?:the\s+)?(?:computer|system|pc|machine)": "shutdown /s /t 5",

    # WiFi & Network
    r"(?:show|list|view)\s+(?:all\s+)?(?:saved\s+)?wifi(?:s)?\s+(?:passwords?|keys?)": _get_telemetry_cmd("wifi"),
    r"(?:show|list)\s+(?:all\s+)?(?:saved\s+)?wifi(?:s)?\s+(?:profiles?|networks?)": "netsh wlan show profiles",
    r"(?:show|get)\s+wifi\s+password\s+(?:for\s+)?(\S+)": 'netsh wlan show profile name="{0}" key=clear',
    r"(?:connect)\s+(?:to\s+)?wifi\s+(\S+)": 'netsh wlan connect name="{0}"',
    r"(?:disconnect)\s+wifi": "netsh wlan disconnect",
    r"(?:show|list)\s+(?:open\s+)?(?:network\s+)?ports": "netstat -an",
    r"(?:check|test)\s+(?:if\s+)?(?:port\s+)?(\d+)\s+(?:is\s+)?(?:open|listening)": "netstat -an | findstr {0}",
    r"(?:trace(?:route)?|tracert)\s+(\S+)": "tracert {0}",
    r"(?:flush|clear)\s+(?:dns|DNS)\s+(?:cache)?": "ipconfig /flushdns",
    r"(?:show|view)\s+(?:dns|DNS)\s+(?:cache)": "ipconfig /displaydns",
    r"(?:release|renew)\s+(?:ip|IP)\s+(?:address)?": "ipconfig /release & ipconfig /renew",
    r"(?:show|view)\s+(?:network\s+)?(?:adapters?|interfaces?)": "ipconfig /all",
    r"(?:show|check)\s+(?:network\s+)?(?:speed|bandwidth)": 'powershell -NoProfile -Command "Get-NetAdapter | Select-Object Name, Status, LinkSpeed"',

    # Services & Startup
    r"(?:show|list)\s+(?:all\s+)?(?:running\s+)?services?": "sc query type= service state= all",
    r"(?:start)\s+service\s+(\S+)": "sc start {0}",
    r"(?:stop)\s+service\s+(\S+)": "sc stop {0}",
    r"(?:restart)\s+service\s+(\S+)": "sc stop {0} & sc start {0}",
    r"(?:show|list)\s+(?:startup|autostart)\s+(?:programs?|apps?)": 'powershell -NoProfile -Command "Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location"',
    r"(?:check|show)\s+(?:startup|boot)\s+(?:time|speed)": 'powershell -NoProfile -Command "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"',

    # Disk & Storage
    r"(?:show|check)\s+(?:disk|drive)\s+(?:health|smart)": "wmic diskdrive get status,model,size",
    r"(?:show|list)\s+(?:all\s+)?(?:drives?|disks?|volumes?)": "wmic logicaldisk get caption,description,freespace,size",
    r"(?:empty|clear)\s+(?:the\s+)?(?:recycle\s+bin|trash)": 'powershell -NoProfile -Command "Clear-RecycleBin -Force"',
    r"(?:show)\s+(?:large|big)\s+files?": 'powershell -NoProfile -Command "Get-ChildItem -Recurse | Sort-Object Length -Descending | Select-Object -First 20 Name, @{N=\'SizeMB\';E={[math]::Round($_.Length/1MB,2)}}"',

    # User & Security
    r"(?:show|list)\s+(?:all\s+)?users?": "net user",
    r"(?:show|view)\s+(?:current\s+)?user\s+(?:info|details)": "whoami /all",
    r"(?:show|view)\s+(?:user\s+)?groups?": "whoami /groups",
    r"(?:lock)\s+(?:the\s+)?(?:screen|computer|pc)": "rundll32.exe user32.dll,LockWorkStation",
    r"(?:show|check)\s+(?:firewall|fw)\s+(?:status|rules?)": "netsh advfirewall show allprofiles",

    # Installed software
    r"(?:show|list)\s+(?:all\s+)?(?:installed\s+)?(?:programs?|software|apps?)": 'powershell -NoProfile -Command "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Select-Object DisplayName, DisplayVersion, Publisher | Sort-Object DisplayName | Format-Table -AutoSize"',
    r"(?:install)\s+(\S+)\s+(?:with|using)\s+winget": "winget install {0}",
    r"(?:uninstall|remove)\s+(\S+)\s+(?:with|using)\s+winget": "winget uninstall {0}",
    r"(?:search|find)\s+(\S+)\s+(?:in|on|with)\s+winget": "winget search {0}",

    # Battery & Power
    r"(?:show|check)\s+(?:battery|power)\s+(?:status|level|info)": 'powershell -NoProfile -Command "Get-CimInstance Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus"',
    r"(?:generate|create)\s+battery\s+(?:report|health)": "powercfg /batteryreport",
    r"(?:show|check)\s+(?:power|energy)\s+(?:plan|scheme)": "powercfg /list",

    # Screen & Display
    r"(?:take\s+(?:a\s+)?)?screenshot": "snippingtool",
    r"(?:show|check)\s+(?:screen\s+)?resolution": 'powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object CurrentHorizontalResolution, CurrentVerticalResolution"',

    # Task & Process management
    r"(?:show|find|which)\s+(?:process|app|program)\s+(?:is\s+)?(?:using|on)\s+(?:port\s+)?(\d+)": "netstat -ano | findstr :{0}",
    r"(?:kill|stop|end)\s+(?:the\s+)?(?:app|program|process)\s+(\S+)": "taskkill /IM {0} /F",
    r"(?:show|check)\s+cpu\s+usage": 'powershell -NoProfile -Command "Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name, CPU, WorkingSet"',
    r"(?:show|check)\s+ram\s+usage": 'powershell -NoProfile -Command "Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10 Name, @{N=\'RAM_MB\';E={[math]::Round($_.WorkingSet/1MB,1)}}"',

    # Virtual Env
    r"(?:activate)\s+(?:the\s+)?(?:virtual\s+)?(?:env|environment|venv)": ".venv\\Scripts\\activate",
    r"(?:create|init)\s+(?:a\s+)?(?:new\s+)?(?:python|pip)\s+(?:virtual\s+)?(?:env|environment|venv)": "python -m venv .venv",

    # Clipboard
    r"(?:copy|save)\s+(?:output|result)\s+(?:to\s+)?clipboard": "| clip",
    r"(?:show|paste|view)\s+clipboard(?:\s+content)?": 'powershell -NoProfile -Command "Get-Clipboard"',
}


# ═══════════════════════════════════════════════════════════
# Translator — Production Engine
# ═══════════════════════════════════════════════════════════

class Translator:
    """
    Production-grade NL → command translator.

    Features:
    - Local pattern matching for common commands (~50 patterns)
    - OS-aware translations (Linux vs Windows)
    - Multi-step command generation
    - Disambiguation for ambiguous requests
    - History-aware caching (successful translations reused)
    - Context-aware prompt building (git, project, env info)
    - Confidence calibration
    - Learn-from-feedback integration
    """

    CONFIDENCE_LOCAL = 0.90    # Pattern-matched locally
    CONFIDENCE_CACHED = 0.95   # From successful history
    CONFIDENCE_LLM = 0.80     # LLM-generated (default)
    CONFIDENCE_MULTI = 0.75   # Multi-step
    _UNSAFE_LOCAL_ARG = re.compile(r"[;&|`$><\n\r]")

    def __init__(self, llm_client, context_manager, history_store):
        self.llm = llm_client
        self.context = context_manager
        self.history = history_store
        self._feedback_corrections: dict[str, str] = {}  # user_input → corrected_cmd
        self._sanitizer = LLMSanitizer()
        self._smart_open = None  # Lazy-loaded to avoid startup cost

    def translate(self, user_input: str, entities: Optional[dict[str, Any]] = None) -> TranslationResult:
        """
        Translate natural language to shell command(s).

        Pipeline:
        1. Check feedback corrections
        2. Check history cache
        3. Try local pattern matching
        4. Fall back to LLM translation
        """
        user_input_clean = user_input.strip()
        if not user_input_clean:
            return TranslationResult(command="", confidence=0, explanation="Empty input")


        # 1. Check if user previously corrected this
        if user_input_clean.lower() in self._feedback_corrections:
            corrected = self._feedback_corrections[user_input_clean.lower()]
            return TranslationResult(
                command=corrected,
                confidence=self.CONFIDENCE_CACHED,
                explanation="Using your previous correction",
                source="feedback",
                provenance=ProvenanceTag(
                    source=ProvenanceSource.CACHED,
                    confidence=self.CONFIDENCE_CACHED,
                    detail="feedback correction",
                    latency_ms=0.1,
                ),
            )

        # 2. Check history for exact NL match
        cached = self._check_history_cache(user_input_clean)
        if cached:
            return cached

        # 2.5. Route open/launch/power intents through SmartOpenEngine
        #      (runs before local patterns so power commands e.g. 'lock screen'
        #       get routed correctly instead of falling through to LLM)
        smart = self._try_smart_open(user_input_clean)
        if smart:
            return smart

        # 3. Try local pattern matching
        local = self._try_local_patterns(user_input_clean)
        if local:
            return local

        # 4. Multi-step detection
        if self._is_multi_step(user_input_clean):
            return self._translate_multi_step(user_input_clean, entities)

        # 5. LLM translation
        return self._llm_translate(user_input_clean, entities)

    def translate_with_disambiguation(self, user_input: str, entities: Optional[dict[str, Any]] = None) -> TranslationResult:
        """Translate with disambiguation when ambiguous."""
        result = self.translate(user_input, entities)

        if result.has_command and result.is_high_confidence:
            return result

        # If low confidence, provide disambiguation options
        if result.has_command and not result.is_high_confidence:
            disambiguations = self._generate_disambiguations(user_input, result)
            result.disambiguation = disambiguations
            result.needs_disambiguation = len(disambiguations) > 1
            return result

        return result

    def learn_correction(self, original_input: str, corrected_command: str):
        """Learn from user correction for future translations."""
        self._feedback_corrections[original_input.strip().lower()] = corrected_command

    def _try_smart_open(self, user_input: str) -> Optional[TranslationResult]:
        """Attempt to route through the SmartOpen Engine for URLs, apps, drives, and power commands."""
        # Lazy load to prevent startup overhead if feature isn't used
        if self._smart_open is None:
            try:
                from intelligence.smart_open import SmartOpenEngine
                self._smart_open = SmartOpenEngine()
            except ImportError:
                return None

        result = self._smart_open.try_resolve(user_input)
        if result:
            return TranslationResult(
                command=result.command,
                confidence=result.confidence,
                explanation=result.explanation,
                source="smart_open",
                provenance=ProvenanceTag(
                    source=ProvenanceSource.PATTERN,
                    confidence=result.confidence,
                    detail=f"smart_open:{result.target_type}",
                    latency_ms=0.1
                )
            )
        return None

    # ═══════════════════════════════════════════════════════
    # Local Pattern Matching
    # ═══════════════════════════════════════════════════════

    def _try_local_patterns(self, user_input: str) -> Optional[TranslationResult]:
        """Try to match against known patterns locally."""
        import platform as plat
        is_windows = plat.system() == "Windows"

        # Compile patterns. LOCAL_PATTERNS first, then WINDOWS_OVERRIDES so overrides take precedence
        patterns = {}
        patterns.update(LOCAL_PATTERNS)
        if is_windows:
            patterns.update(WINDOWS_OVERRIDES)

        def _resolve_match(m, p_str, tpl):
            command = tpl
            if "{" in command and "}" in command and m.groups():
                try:
                    if re.search(r"\{\d+\}", command):
                        # Safety gate: reject if any captured group contains shell metacharacters
                        if any(self._has_unsafe_local_chars(g) for g in m.groups() if g):
                            return None
                        command = command.format(*m.groups())
                except Exception:
                    pass
            command = re.sub(r'\s+', ' ', command).strip()
            return TranslationResult(
                command=command,
                confidence=self.CONFIDENCE_LOCAL,
                explanation=f"Matched pattern: {str(p_str)[:50]}",
                source="local",
                provenance=ProvenanceTag(
                    source=ProvenanceSource.PATTERN,
                    confidence=self.CONFIDENCE_LOCAL,
                    detail="local pattern match",
                    latency_ms=0.1,
                ),
            )

        # Pass 1: Exact matches (highest priority)
        for pattern, template in patterns.items():
            match = re.match(pattern + r"$", user_input, re.IGNORECASE)
            if match:
                return _resolve_match(match, pattern, template)

        # Pass 2 removed: Prefix matching overrides complex natural language queries.
        # By removing this, incomplete/complex sentences naturally fall through to the LLM.

        dynamic = self._try_local_dynamic_patterns(user_input, is_windows)
        if dynamic:
            return TranslationResult(
                command=dynamic,
                confidence=self.CONFIDENCE_LOCAL,
                explanation="Matched dynamic local pattern",
                source="local",
                provenance=ProvenanceTag(
                    source=ProvenanceSource.PATTERN,
                    confidence=self.CONFIDENCE_LOCAL,
                    detail="dynamic local pattern match",
                    latency_ms=0.1,
                ),
            )

        return None



    def _try_local_dynamic_patterns(self, user_input: str, is_windows: bool) -> Optional[str]:
        """Handle dynamic local patterns with argument-safe command rendering."""
        patterns: list[tuple[str, Callable[..., Optional[str]]]] = [
            (r"(?:show|list|view)\s+(?:all\s+)?files?(?:\s+in\s+(.+))?", lambda g: self._build_cmd(["dir" if is_windows else "ls", g[0].strip()] if g and g[0] else ["dir" if is_windows else "ls"])),
            (r"(?:make|create)\s+(?:a\s+)?(?:directory|folder|dir)\s+(?:called\s+)?(\S+)", lambda g: self._build_cmd(["mkdir", g[0]])),
            (r"(?:delete|remove)\s+(?:the\s+)?(?:file|directory|folder)\s+(\S+)", lambda g: self._build_cmd(["rm", g[0]])),
            (r"(?:copy|cp)\s+(\S+)\s+(?:to\s+)?(\S+)", lambda g: self._build_cmd(["cp", g[0], g[1]])),
            (r"(?:move|mv|rename)\s+(\S+)\s+(?:to\s+)?(\S+)", lambda g: self._build_cmd(["mv", g[0], g[1]])),
            (r"(?:show|display|cat|view)\s+(?:the\s+)?(?:contents?\s+of\s+)?(\S+)", lambda g: self._build_cmd(["cat", g[0]])),
            (r"(?:find|search|locate)\s+(?:files?\s+)?(?:named?\s+)?(\S+)", lambda g: self._build_cmd(["dir", "/s", "/b", f"*{g[0]}*"]) if is_windows else self._build_cmd(["find", ".", "-name", f"*{g[0]}*"])),
            (r"(?:count|how many)\s+(?:lines?\s+in)\s+(\S+)", lambda g: self._build_cmd(["wc", "-l", g[0]])),
            (r"(?:go|change|cd|switch)\s+(?:to\s+)?(?:directory\s+)?(\S+)", lambda g: self._build_cmd(["cd", g[0]])),
            (r"(?:create|make)\s+(?:a\s+)?(?:new\s+)?branch\s+(?:called\s+)?(\S+)", lambda g: self._build_cmd(["git", "checkout", "-b", g[0]])),
            (r"(?:switch|checkout)\s+(?:to\s+)?(?:branch\s+)?(\S+)", lambda g: self._build_cmd(["git", "checkout", g[0]])),
            (r"(?:commit|save)\s+(?:with\s+)?(?:message\s+)?['\"](.+)['\"]", lambda g: self._build_cmd(["git", "commit", "-m", g[0]])),
            (r"(?:kill|stop)\s+process\s+(\d+)", lambda g: self._build_cmd(["taskkill", "/PID", g[0], "/F"]) if is_windows else self._build_cmd(["kill", g[0]])),
            (r"install\s+(?:package\s+)?(\S+)(?:\s+(?:with|using)\s+pip)?", lambda g: self._build_cmd(["pip", "install", g[0]])),
            (r"uninstall\s+(?:package\s+)?(\S+)", lambda g: self._build_cmd(["pip", "uninstall", g[0]])),
            (r"(?:stop|halt)\s+(?:docker\s+)?container\s+(\S+)", lambda g: self._build_cmd(["docker", "stop", g[0]])),
            (r"(?:start|run)\s+(?:docker\s+)?container\s+(\S+)", lambda g: self._build_cmd(["docker", "start", g[0]])),
            # GitHub clone with owner/repo shorthand
            (r"(?:clone|git\s+clone)\s+([\w.-]+/[\w.-]+)", lambda g: self._build_cmd(["git", "clone", f"https://github.com/{g[0]}.git"])),
            # GitHub clone with full URL
            (r"(?:clone|git\s+clone)\s+(https?://\S+)", lambda g: self._build_cmd(["git", "clone", g[0]])),
        ]

        for pattern, builder in patterns:
            match = re.match(pattern + r"$", user_input, re.IGNORECASE)
            if not match:
                continue

            groups = tuple((g or "").strip() for g in match.groups())
            if any(self._has_unsafe_local_chars(g) for g in groups if g):
                continue

            try:
                command = builder(groups)
            except Exception:
                continue

            if command:
                return re.sub(r'\s+', ' ', command).strip()

        return None

    def _build_cmd(self, parts: list[str]) -> str:
        """Build a shell command from parts with safe argument escaping."""
        if not parts:
            return ""

        executable = parts[0]
        remaining: list[str] = list(parts[1:])  # type: ignore[index]
        args: list[str] = [self._escape_local_arg(p) for p in remaining if p is not None and p != ""]
        return " ".join([executable, *args]).strip()

    def _escape_local_arg(self, value: str) -> str:
        """Escape local command argument conservatively across platforms."""
        if re.match(r"^[A-Za-z0-9._/\\:-]+$", value):
            return value

        if os.name == "nt":
            return subprocess.list2cmdline([value])

        return shlex.quote(value)

    def _has_unsafe_local_chars(self, value: str) -> bool:
        """Return True when an input segment contains shell control characters."""
        return bool(self._UNSAFE_LOCAL_ARG.search(value))

    # ═══════════════════════════════════════════════════════
    # Multi-step Translation
    # ═══════════════════════════════════════════════════════

    def _is_multi_step(self, user_input: str) -> bool:
        """Detect if input requires multiple commands."""
        multi_keywords = [
            "and then", "also", "after that", "followed by",
            "first", "next", "finally", "step"
        ]
        return any(kw in user_input.lower() for kw in multi_keywords)

    def _translate_multi_step(self, user_input: str, entities: Optional[dict[str, Any]] = None) -> TranslationResult:
        """Translate a multi-step request into multiple commands."""
        ctx_summary = self.context.get_context_summary()

        prompt = f"""Translate this multi-step request into individual shell commands.
Context: {ctx_summary}
Request: {user_input}

Return JSON:
{{
    "steps": [
        {{"command": "cmd1", "explanation": "what it does", "order": 1}},
        {{"command": "cmd2", "explanation": "what it does", "order": 2}}
    ],
    "confidence": 0.8
}}"""

        result = self.llm.generate_json(prompt, "You are a shell command translator. Return JSON only.")

        if not result:
            return self._llm_translate(user_input, entities)

        steps_data = result.get("steps", [])
        steps = [
            TranslationStep(
                command=s.get("command", ""),
                explanation=s.get("explanation", ""),
                order=s.get("order", i),
                condition=s.get("condition", "on_success"),
            )
            for i, s in enumerate(steps_data)
        ]

        combined = " && ".join(s.command for s in steps if s.command)
        confidence = float(result.get("confidence", self.CONFIDENCE_MULTI))

        input_preview: str = str(user_input)[:50]  # type: ignore[index]
        return TranslationResult(
            command=combined,
            confidence=confidence,
            explanation=f"Multi-step: {len(steps)} commands",
            is_multi_step=True,
            steps=steps,
            source="llm_multi",
            provenance=ProvenanceTag(
                source=ProvenanceSource.LLM,
                confidence=confidence,
                detail=f"multi-step from: '{input_preview}'",
            ),
        )

    # ═══════════════════════════════════════════════════════
    # LLM Translation
    # ═══════════════════════════════════════════════════════

    def _llm_translate(self, user_input: str, entities: Optional[dict[str, Any]] = None) -> TranslationResult:
        """Use LLM for command translation."""
        ctx_summary = self.context.get_context_summary()
        recent = self.history.get_recent(5)
        history_str = "\n".join(f"  {r.command}" for r in recent)

        entity_hint = ""
        if entities:
            parts = []
            for etype, values in entities.items():
                if values:
                    entry: str = f"{etype}: {', '.join(str(v) for v in values)}"
                    parts.append(entry)  # type: ignore[arg-type]
            if parts:
                entity_hint = f"\n\nExtracted entities: {'; '.join(parts)}"

        from llm.prompts import translate_prompt  # type: ignore
        system, user = translate_prompt(user_input + entity_hint, ctx_summary, history_str)

        start = time.time()
        result = self.llm.generate_json(user, system)
        latency = (time.time() - start) * 1000

        if not result:
            return TranslationResult(
                command="",
                confidence=0.0,
                explanation="Could not translate — LLM unavailable",
                provenance=ProvenanceTag(
                    source=ProvenanceSource.FALLBACK,
                    confidence=0.0,
                    latency_ms=latency,
                ),
            )

        command = result.get("command", "")
        confidence = min(float(result.get("confidence", 0.5)), 1.0)
        explanation = result.get("explanation", "")
        is_destructive = result.get("is_destructive", False)
        alternatives = result.get("alternatives", [])

        # ── Post-LLM Sanitization Gate ──
        sanitized = self._sanitizer.sanitize(command, source="llm")
        if not sanitized.is_safe:
            return TranslationResult(
                command="",
                confidence=0.0,
                explanation=f"LLM command blocked by sanitizer: {'; '.join(sanitized.warnings)}",
                is_destructive=True,
                source="sanitizer_blocked",
                provenance=ProvenanceTag(
                    source=ProvenanceSource.FALLBACK,
                    confidence=0.0,
                    detail="blocked by LLM sanitizer",
                    latency_ms=latency,
                ),
            )
        if sanitized.was_modified:
            command = sanitized.command

        return TranslationResult(
            command=sanitized.command,
            confidence=confidence,
            explanation=explanation,
            is_destructive=is_destructive,
            alternatives=alternatives,
            source="llm",
            provenance=ProvenanceTag(
                source=ProvenanceSource.LLM,
                confidence=confidence,
                latency_ms=latency,
            ),
        )

    # ═══════════════════════════════════════════════════════
    # Swarm Translation
    # ═══════════════════════════════════════════════════════

    def _swarm_translate(self, user_input: str) -> TranslationResult:
        """Route complex intentions through the Swarm Orchestrator."""
        start = time.time()
        
        # Fire Swarm Pipeline
        swarm_res = self.swarm.route_task(user_input)
        latency = (time.time() - start) * 1000
        
        # Sanitize result
        sanitized = self._sanitizer.sanitize(swarm_res.final_command, source="swarm")
        if not sanitized.is_safe or not swarm_res.is_safe:
            return TranslationResult(
                command="",
                confidence=0.0,
                explanation=swarm_res.explanation + f" [Sanitizer block: {'; '.join(sanitized.warnings)}]",
                is_destructive=True,
                source="swarm_blocked",
                provenance=ProvenanceTag(
                    source=ProvenanceSource.FALLBACK,
                    confidence=0.0,
                    latency_ms=latency,
                )
            )

        return TranslationResult(
            command=sanitized.command,
            confidence=0.95, # High confidence because Verified
            explanation=f"Swarm Executed [{', '.join(swarm_res.agents_used)}]:\n" + swarm_res.explanation,
            is_destructive=True, # Complex operations are treated as destructive by default
            source="swarm",
            provenance=ProvenanceTag(
                source=ProvenanceSource.LLM,
                confidence=0.95,
                latency_ms=latency,
                detail="multi-agent verification",
            )
        )

    # ═══════════════════════════════════════════════════════
    # Disambiguation
    # ═══════════════════════════════════════════════════════

    def _generate_disambiguations(self, user_input: str, result: TranslationResult) -> list[dict]:
        """Generate disambiguation options for ambiguous requests."""
        options = [{"command": result.command, "description": result.explanation}]

        if result.alternatives:
            alts: list[str] = list(result.alternatives)[:3]  # type: ignore[index]
            for alt in alts:
                options.append({"command": alt, "description": f"Alternative: {alt}"})

        return options

    # ═══════════════════════════════════════════════════════
    # History Cache
    # ═══════════════════════════════════════════════════════

    def _check_history_cache(self, user_input: str) -> Optional[TranslationResult]:
        """Check if we've translated this exact input before."""
        try:
            records = self.history.search_commands(user_input, limit=5)
            for record in records:
                if record.original_nl and record.original_nl.lower() == user_input.lower():
                    if record.exit_code == 0:
                        return TranslationResult(
                            command=record.command,
                            confidence=self.CONFIDENCE_CACHED,
                            explanation="Previously translated successfully",
                            source="cached",
                            provenance=ProvenanceTag(
                                source=ProvenanceSource.CACHED,
                                confidence=self.CONFIDENCE_CACHED,
                                detail="exact NL match from history",
                                latency_ms=0.1,
                            ),
                        )
        except Exception:
            pass
        return None
