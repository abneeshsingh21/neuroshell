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

def _get_internal_cmd(script_name: str, arg: str) -> str:
    import sys
    import os
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        script_path = os.path.join(sys._MEIPASS, "intelligence", script_name)
    else:
        # Use absolute path based on this file's location to be independent of cwd
        base_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(base_dir, script_name)
    return f'python "{script_path}" {arg}'

def _get_telemetry_cmd(arg: str) -> str:
    return _get_internal_cmd("ui_telemetry.py", arg)

def _get_deep_search_cmd(arg: str) -> str:
    return _get_internal_cmd("deep_search.py", arg)


LOCAL_PATTERNS = {
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

    # File operations — flexible natural language
    r"(?:show|list|view|ls)\s+(?:all\s+)?files?(?:\s+in\s+(.+))?": "ls {0}",
    r"(?:make|create|new)\s+(?:a\s+)?(?:new\s+)?(?:directory|folder|dir)\s+(?:(?:called|name|named|with\s+name)\s+)?(\S+)": "mkdir {0}",
    r"(?:new|create|make)\s+(?:a\s+)?(?:new\s+)?folder\s+(\S+)": "mkdir {0}",
    r"(?:make|create|new)\s+(?:a\s+)?(?:new\s+)?(?:file)\s+(?:(?:called|name|named)\s+)?(\S+)": "touch {0}",
    r"(?:delete|remove|rm)\s+(?:the\s+)?(?:file|directory|folder)?\s*(\S+)": "rm {0}",
    r"(?:copy|cp)\s+(\S+)\s+(?:to\s+)?(\S+)": "cp {0} {1}",
    r"(?:move|mv|rename)\s+(\S+)\s+(?:to\s+)?(\S+)": "mv {0} {1}",
    r"(?:show|display|cat|read|view|open)\s+(?:the\s+)?(?:contents?\s+of\s+)?(?:file\s+)?(\S+\.\S+)": "cat {0}",
    r"(?:find|search|locate)\s+(?:files?\s+)?(?:named?\s+)?(\S+)": "find . -name '*{0}*'",
    r"(?:count|how many)\s+(?:lines?\s+in)\s+(\S+)": "wc -l {0}",
    r"(?:show|what(?:'s| is)|where\s+am\s+i)\s*(?:the\s+)?(?:current\s+)?(?:directory|dir|pwd|location|path)?": "pwd",
    r"(?:go|change|cd|switch|navigate)\s+(?:to\s+)?(?:directory\s+)?(\S+)": "cd {0}",
    r"go\s+(?:back|up)(?:\s+one)?(?:\s+(?:directory|folder|level))?": "cd ..",
    r"(?:show|view)\s+(?:the\s+)?(?:size|sizes)\s+(?:of\s+)?(?:all\s+)?(?:files?|folders?|directories)": "du -sh *",
    r"(?:show|view)\s+(?:folder\s+)?(?:tree|structure)": "tree",
    r"(?:compress|zip)\s+(\S+)": "zip -r {0}.zip {0}",
    r"(?:extract|unzip)\s+(\S+)": "unzip {0}",
    r"(?:compare|diff)\s+(\S+)\s+(?:and|with|vs)\s+(\S+)": "diff {0} {1}",
    r"(?:find|search)\s+(?:for\s+)?(.+?)\s+in\s+(\S+)": "grep -r '{0}' {1}",

    r"(?:search|grep|find)\s+(?:for\s+)?(.+?)\s+(?:in\s+)?(?:all\s+)?files?": "grep -r '{0}' .",

    r"(?:write|echo|put)\s+['\"](.+?)['\"]\s+(?:to|in|into)\s+(\S+)": "echo '{0}' > {1}",
    r"(?:append|add)\s+['\"](.+?)['\"]\s+(?:to|in|into)\s+(\S+)": "echo '{0}' >> {1}",
    r"(?:empty|truncate|clear)\s+(?:the\s+)?(?:file\s+)?(\S+\.\S+)": "echo. > {0}",
    r"(?:head|first)\s+(\d+)\s+(?:lines?\s+(?:of|in|from)\s+)?(\S+)": "head -n {0} {1}",
    r"(?:tail|last)\s+(\d+)\s+(?:lines?\s+(?:of|in|from)\s+)?(\S+)": "tail -n {0} {1}",

    # Git operations
    r"(?:what(?:'s| is)|show|check)\s+(?:the\s+)?(?:git\s+)?status": "git status",
    r"(?:show|list)\s+(?:all\s+)?(?:git\s+)?branches": "git branch -a",
    r"(?:create|make|new)\s+(?:a\s+)?(?:new\s+)?branch\s+(?:(?:called|named|name)\s+)?(\S+)": "git checkout -b {0}",
    r"(?:switch|checkout)\s+(?:to\s+)?(?:branch\s+)?(\S+)": "git checkout {0}",
    r"(?:commit|save)\s+(?:with\s+)?(?:message\s+)?['\"](.+)['\"]": 'git commit -m "{0}"',
    r"(?:commit|save)\s+(?:all|everything)(?:\s+(?:with\s+)?(?:message\s+)?['\"](.+)['\"])?": 'git add -A && git commit -m "{0}"',
    r"(?:push|upload)\s+(?:to\s+)?(?:remote|origin|github)?": "git push",
    r"(?:git\s+)?(?:pull|fetch)(?:\s+(?:from\s+)?(?:remote|origin))?": "git pull",
    r"(?:update|sync)\s+(?:git\s+)?(?:repo(?:sitory)?|branch|code)(?:\s+from\s+(?:remote|origin))?": "git pull",
    r"(?:show|view)\s+(?:recent\s+)?(?:git\s+)?(?:log|history|commits)": "git log --oneline -10",
    r"(?:stash|save)\s+(?:my\s+)?changes": "git stash",
    r"(?:pop|restore)\s+(?:stashed?\s+)?changes": "git stash pop",
    r"(?:add|stage)\s+all\s+(?:files?|changes)": "git add -A",
    r"(?:add|stage)\s+(\S+)": "git add {0}",
    r"(?:undo|revert)\s+(?:the\s+)?(?:last\s+)?commit": "git reset --soft HEAD~1",
    r"(?:show|view)\s+(?:git\s+)?diff": "git diff",
    r"(?:discard|reset)\s+(?:all\s+)?(?:unstaged\s+)?changes": "git checkout -- .",
    r"(?:clone|git clone)\s+(https?://\S+)": "git clone {0}",
    r"(?:clone|git clone)\s+([\w.-]+/[\w.-]+)": "git clone https://github.com/{0}.git",
    r"(?:clone)\s+(\S+)": "git clone {0}",
    r"(?:delete|remove)\s+branch\s+(\S+)": "git branch -d {0}",
    r"(?:merge)\s+(?:branch\s+)?(\S+)": "git merge {0}",
    r"(?:show|list)\s+(?:git\s+)?(?:remote|remotes)": "git remote -v",
    r"(?:show|list)\s+(?:git\s+)?tags?": "git tag",
    r"(?:what|which)\s+branch\s+(?:am i|is this)(?:\s+on)?": "git branch --show-current",
    r"(?:show|list)\s+(?:git\s+)?(?:changed|modified)\s+files?": "git diff --name-only",
    r"(?:blame|who\s+(?:changed|edited|wrote))\s+(\S+)": "git blame {0}",

    # System operations
    r"(?:show|what)\s+(?:is\s+)?(?:free\s+)?(?:disk\s+)?space": "df -h",
    r"(?:show|what)\s+(?:is\s+)?memory\s+usage": "free -h",
    r"(?:who\s+am\s+i|current\s+user|whoami)": "whoami",
    r"(?:what(?:'s| is)|show)\s+(?:the\s+)?(?:system\s+)?(?:date|time)": "date",
    r"(?:show|list)\s+(?:running\s+)?processes": "ps aux",
    r"(?:kill|stop)\s+process\s+(\d+)": "kill {0}",
    r"(?:find|show)\s+(?:my\s+)?(?:ip|IP)\s+(?:address)?": "ip addr show",
    r"(?:check|test)\s+(?:internet|network|connectivity)\s*(?:connection)?": "ping -c 4 8.8.8.8",
    r"(?:show|what)\s+(?:is\s+)?(?:system\s+)?uptime": "uptime",
    r"(?:show|list)\s+(?:all\s+)?environment\s+variables?": "env",
    r"(?:clear|cls)(?:\s+(?:the\s+)?(?:screen|terminal|console))?": "clear",
    r"(?:show|what)\s+(?:is\s+)?(?:my\s+)?hostname": "hostname",
    r"(?:restart|reboot)\s+(?:the\s+)?(?:computer|system|pc|machine)": "shutdown -r",
    r"(?:shutdown|turn off|power off)\s+(?:the\s+)?(?:computer|system|pc|machine)": "shutdown -s",

    # Package management
    r"(?:pip\s+)?install\s+(?:package\s+)?(\S+)(?:\s+(?:with|using)\s+pip)?": "pip install {0}",
    r"(?:pip\s+)?uninstall\s+(?:package\s+)?(\S+)": "pip uninstall {0}",
    r"(?:list|show)\s+(?:installed\s+)?(?:pip\s+)?packages": "pip list",
    r"(?:update|upgrade)\s+(?:all\s+)?(?:pip\s+)?packages?": "pip install --upgrade pip",
    r"(?:install|add)\s+(\S+)\s+(?:with|using)\s+npm": "npm install {0}",
    r"npm\s+install\s+(\S+)": "npm install {0}",
    r"(?:list|show)\s+npm\s+packages": "npm list",
    r"(?:run|start)\s+(?:npm\s+)?(?:dev|development)\s+(?:server)?": "npm run dev",
    r"(?:run|start)\s+(?:the\s+)?(?:server|app|application)": "npm start",
    r"(?:build|compile)\s+(?:the\s+)?(?:project|app)": "npm run build",
    r"(?:create|init)\s+(?:a\s+)?(?:new\s+)?(?:node|npm)\s+project": "npm init -y",
    r"(?:create|init)\s+(?:a\s+)?(?:new\s+)?(?:react)\s+(?:app|project)(?:\s+(?:called|named)\s+(\S+))?": "npx create-react-app {0}",
    r"(?:create|init)\s+(?:a\s+)?(?:new\s+)?(?:vite)\s+(?:app|project)": "npm create vite@latest",
    r"(?:create|init)\s+(?:a\s+)?(?:new\s+)?(?:next\.?js?)\s+(?:app|project)": "npx create-next-app@latest",
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
    r"docker\s+compose\s+down": "docker compose down",

    # Python operations
    r"run\s+(?:the\s+)?(?:python\s+)?(?:script\s+)?(\S+\.py)": "python {0}",
    r"run\s+(?:the\s+)?(?:tests?|pytest)": "python -m pytest",
    r"(?:check|show|what(?:'s| is))\s+(?:the\s+)?python\s+version": "python --version",
    r"(?:check|show|what(?:'s| is))\s+(?:the\s+)?node\s+version": "node --version",
    r"(?:run|start)\s+(?:flask|django)\s+(?:server|app)": "python -m flask run",
    r"(?:format|lint)\s+(?:the\s+)?(?:code|python)": "python -m black .",
    r"(?:freeze|export)\s+(?:pip\s+)?(?:requirements|deps|dependencies)": "pip freeze > requirements.txt",
    r"install\s+(?:from\s+)?requirements": "pip install -r requirements.txt",
    r"(?:run|execute)\s+(\S+\.py)": "python {0}",
    r"(?:run|execute)\s+(\S+\.js)": "node {0}",
    r"(?:run|execute)\s+(\S+\.sh)": "bash {0}",

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
    r"(?:calculate|calc|math)\s+([\d\s\+\-\*\/\(\)\.\%\^]+)": "python -c \"print({0})\"",

    # ── Permissions & ownership ──
    r"(?:change|set)\s+(?:permissions?\s+(?:of\s+)?)?(\S+)\s+(?:to\s+)?(\d{3})": "chmod {1} {0}",
    r"(?:change|set)\s+owner\s+(?:of\s+)?(\S+)\s+(?:to\s+)?(\S+)": "chown {1} {0}",
    r"(?:change|set)\s+group\s+(?:of\s+)?(\S+)\s+(?:to\s+)?(\S+)": "chgrp {1} {0}",

    # ── Archives & compression ──
    r"(?:create|make)\s+(?:a\s+)?tar(?:ball)?\s+(?:of\s+)?(\S+)": "tar -czf {0}.tar.gz {0}",
    r"(?:extract|untar)\s+(\S+\.tar\.gz)": "tar -xzf {0}",
    r"(?:extract|untar)\s+(\S+\.tar\.bz2)": "tar -xjf {0}",
    r"(?:extract|untar)\s+(\S+\.tar)": "tar -xf {0}",
    r"(?:create|make)\s+(?:a\s+)?zip\s+(?:of\s+)?(\S+)": "zip -r {0}.zip {0}",
    r"(?:extract|unzip)\s+(\S+\.zip)": "unzip {0}",

    # ── SSH & Remote ──
    r"(?:ssh|connect)\s+(?:to\s+)?(\S+@\S+)": "ssh {0}",
    r"(?:copy|scp|transfer)\s+(\S+)\s+(?:to\s+)?(?:remote\s+)?(\S+@\S+:\S+)": "scp {0} {1}",
    r"(?:copy|scp)\s+(?:from\s+)?(?:remote\s+)?(\S+@\S+:\S+)\s+(?:to\s+)?(\S+)": "scp {0} {1}",
    r"(?:generate|create)\s+(?:ssh\s+)?key(?:pair)?": "ssh-keygen -t ed25519",

    # ── Cron & scheduling ──
    r"(?:show|list|view)\s+(?:my\s+)?(?:cron\s+)?(?:jobs|crontab|scheduled\s+tasks?)": "crontab -l",
    r"(?:edit)\s+(?:my\s+)?(?:cron\s+)?(?:jobs|crontab)": "crontab -e",

    # ── Text & data processing ──
    r"(?:sort)\s+(?:the\s+)?(?:file\s+)?(\S+)": "sort {0}",
    r"(?:sort)\s+(\S+)\s+(?:uniquely|unique)": "sort -u {0}",
    r"(?:remove|delete)\s+(?:duplicate|dup)\s+(?:lines?\s+)?(?:in|from)\s+(\S+)": "sort -u {0}",
    r"(?:count)\s+(?:words?\s+in)\s+(\S+)": "wc -w {0}",
    r"(?:replace|substitute)\s+['\"](.+?)['\"]\s+(?:with)\s+['\"](.+?)['\"]\s+(?:in)\s+(\S+)": "sed -i 's/{0}/{1}/g' {2}",
    r"(?:show|print)\s+(?:line\s+)?(\d+)\s+(?:of|from|in)\s+(\S+)": "sed -n '{0}p' {1}",
    r"(?:reverse|tac)\s+(?:the\s+)?(?:file\s+)?(\S+)": "tac {0}",
    r"(?:show|print)\s+(?:unique|distinct)\s+(?:lines?\s+)?(?:in|from)\s+(\S+)": "sort -u {0}",
    r"(?:cut|extract)\s+(?:column|field)\s+(\d+)\s+(?:from|in|of)\s+(\S+)": "cut -f{0} {1}",

    # ── Disk & storage ──
    r"(?:check|show)\s+(?:disk\s+)?(?:usage|size)\s+(?:of\s+)?(\S+)": "du -sh {0}",
    r"(?:show|find)\s+(?:top|largest|biggest)\s+(\d+)\s+files?": "find . -type f -exec du -h {{}} + | sort -rh | head -n {0}",
    r"(?:show|find)\s+(?:files?\s+)?(?:larger|bigger)\s+(?:than)\s+(\S+)": "find . -size +{0} -type f",
    r"(?:show|check)\s+(?:inode|inodes)\s+(?:usage)?": "df -i",

    # ── User & session ──
    r"(?:show|who)\s+(?:is\s+)?(?:logged\s+in|online)": "who",
    r"(?:show|view)\s+(?:login\s+)?history": "last",
    r"(?:add|create)\s+(?:a\s+)?(?:new\s+)?user\s+(\S+)": "sudo useradd {0}",
    r"(?:delete|remove)\s+user\s+(\S+)": "sudo userdel {0}",
    r"(?:change|set|reset)\s+password\s+(?:for\s+)?(\S+)": "sudo passwd {0}",

    # ── Hardware & performance ──
    r"(?:show|check)\s+(?:cpu|processor)\s+(?:info|details?)": "lscpu",
    r"(?:show|check)\s+(?:gpu|graphics)\s+(?:info|details?)": "lspci | grep -i vga",
    r"(?:show|check)\s+(?:usb)\s+(?:devices?)": "lsusb",
    r"(?:show|check)\s+(?:pci)\s+(?:devices?)": "lspci",
    r"(?:show|check)\s+(?:block\s+)?(?:devices?|disks?)": "lsblk",
    r"(?:show|check)\s+(?:hardware)\s+(?:info|details?)": "lshw",

    # ── Kubernetes ──
    r"(?:show|list|get)\s+(?:all\s+)?(?:k8s\s+|kube\s+)?pods?": "kubectl get pods",
    r"(?:show|list|get)\s+(?:all\s+)?(?:k8s\s+|kube\s+)?services?": "kubectl get svc",
    r"(?:show|list|get)\s+(?:all\s+)?(?:k8s\s+|kube\s+)?(?:deployments?|deploys?)": "kubectl get deployments",
    r"(?:show|list|get)\s+(?:all\s+)?(?:k8s\s+|kube\s+)?(?:namespaces?|ns)": "kubectl get ns",
    r"(?:show|view)\s+(?:k8s\s+|kube\s+)?(?:pod\s+)?logs?\s+(?:for\s+)?(\S+)": "kubectl logs {0}",
    r"(?:describe)\s+(?:k8s\s+|kube\s+)?pod\s+(\S+)": "kubectl describe pod {0}",
    r"(?:exec|shell)\s+(?:into\s+)?(?:k8s\s+|kube\s+)?pod\s+(\S+)": "kubectl exec -it {0} -- /bin/sh",

    # ── Terraform ──
    r"(?:terraform|tf)\s+(?:init|initialize)": "terraform init",
    r"(?:terraform|tf)\s+(?:plan|preview)": "terraform plan",
    r"(?:terraform|tf)\s+(?:apply)": "terraform apply",
    r"(?:terraform|tf)\s+(?:destroy)": "terraform destroy",
    r"(?:terraform|tf)\s+(?:show|state)": "terraform show",

    # ── Security & forensics ──
    r"(?:hash|checksum|sha256)\s+(?:of\s+)?(\S+)": "sha256sum {0}",
    r"(?:md5)\s+(?:of\s+)?(\S+)": "md5sum {0}",
    r"(?:encrypt)\s+(?:file\s+)?(\S+)": "openssl enc -aes-256-cbc -salt -in {0} -out {0}.enc",
    r"(?:decrypt)\s+(?:file\s+)?(\S+)": "openssl enc -aes-256-cbc -d -in {0} -out {0}.dec",
    r"(?:check|verify)\s+(?:ssl|tls)\s+(?:cert(?:ificate)?\s+)?(?:for\s+)?(\S+)": "openssl s_client -connect {0}:443 -servername {0} 2>/dev/null | openssl x509 -noout -dates -subject",
    r"(?:create|generate)\s+(?:self[- ]?signed\s+)?(?:ssl\s+)?cert(?:ificate)?": "openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes",
    r"(?:find)\s+(?:all\s+)?(?:world[- ]?writable|777)\s+files?": "find / -type f -perm -o+w 2>/dev/null",
    r"(?:find)\s+(?:all\s+)?suid\s+files?": "find / -perm -4000 -type f 2>/dev/null",
    r"(?:scan|check)\s+(?:open\s+)?ports?\s+(?:on\s+)?(\S+)": "nmap -sT {0}",
    r"(?:show|find)\s+(?:failed|bad)\s+(?:login|ssh)\s+attempts?": "grep -i 'failed' /var/log/auth.log | tail -20",
    r"(?:show|list)\s+(?:all\s+)?(?:listening)\s+(?:ports?|sockets?)": "ss -tulpn",
    r"(?:monitor|watch)\s+(?:network\s+)?(?:traffic|packets?)(?:\s+on\s+(\S+))?": "tcpdump -i {0}",
    r"(?:show|check)\s+(?:file\s+)?(?:permissions?|perms?)\s+(?:of\s+)?(\S+)": "ls -la {0}",

    # ── Database operations ──
    r"(?:show|list)\s+(?:all\s+)?(?:mysql\s+)?databases?": "mysql -e 'SHOW DATABASES;'",
    r"(?:show|list)\s+(?:all\s+)?(?:mysql\s+)?tables?\s+(?:in\s+)?(\S+)": "mysql -e 'USE {0}; SHOW TABLES;'",
    r"(?:show|list)\s+(?:all\s+)?(?:postgres|pg)\s+databases?": "psql -l",
    r"(?:show|list)\s+(?:all\s+)?(?:postgres|pg)\s+tables?": "psql -c '\\dt'",
    r"(?:check|show)\s+(?:postgres|pg|mysql|db)\s+(?:database\s+)?size": "psql -c \"SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) FROM pg_database;\"",
    r"(?:dump|backup)\s+(?:database\s+)?(\S+)\s+(?:to\s+)?(\S+)": "pg_dump {0} > {1}",
    r"(?:restore)\s+(?:database\s+)?(\S+)\s+(?:from\s+)?(\S+)": "psql {0} < {1}",
    r"(?:show|list)\s+(?:redis)\s+keys?": "redis-cli KEYS '*'",
    r"(?:show|check)\s+(?:redis)\s+(?:info|status)": "redis-cli INFO",
    r"(?:show|list)\s+(?:mongo(?:db)?\s+)?(?:databases?|collections?)": "mongosh --eval 'show dbs'",

    # ── AWS CLI ──
    r"(?:list|show)\s+(?:all\s+)?(?:aws\s+)?s3\s+buckets?": "aws s3 ls",
    r"(?:list|show)\s+(?:aws\s+)?s3\s+(?:contents?\s+of\s+)?(\S+)": "aws s3 ls s3://{0}",
    r"(?:upload|copy)\s+(\S+)\s+(?:to\s+)?(?:aws\s+)?s3[:/]+(\S+)": "aws s3 cp {0} s3://{1}",
    r"(?:download|copy)\s+(?:from\s+)?(?:aws\s+)?s3[:/]+(\S+)\s+(?:to\s+)?(\S+)": "aws s3 cp s3://{0} {1}",
    r"(?:list|show)\s+(?:all\s+)?(?:aws\s+)?ec2\s+instances?": "aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId,State.Name,InstanceType]' --output table",
    r"(?:list|show)\s+(?:all\s+)?(?:aws\s+)?lambda\s+functions?": "aws lambda list-functions --query 'Functions[*].FunctionName' --output table",
    r"(?:show|check)\s+(?:aws\s+)?(?:iam\s+)?(?:who am i|identity|caller)": "aws sts get-caller-identity",

    # ── Performance & monitoring ──
    r"(?:monitor|watch)\s+(?:cpu|system)\s+(?:usage\s+)?(?:in\s+)?(?:real[- ]?time|live)": "top",
    r"(?:monitor|watch)\s+(?:disk\s+)?(?:io|i/o)\s+(?:in\s+)?(?:real[- ]?time|live)?": "iostat -x 1",
    r"(?:monitor|watch)\s+(?:network\s+)?(?:io|bandwidth|traffic)": "iftop",
    r"(?:show|check)\s+(?:system\s+)?load\s+(?:average)?": "uptime",
    r"(?:benchmark|test)\s+(?:disk\s+)?(?:speed|io|performance)": "dd if=/dev/zero of=testfile bs=1M count=1024 oflag=direct 2>&1; rm -f testfile",
    r"(?:show|list)\s+(?:all\s+)?(?:open\s+)?files?\s+(?:by|for)\s+(?:process\s+)?(\S+)": "lsof -p {0}",
    r"(?:show|find)\s+(?:files?\s+)?(?:modified|changed)\s+(?:in\s+)?(?:the\s+)?(?:last\s+)?(\d+)\s+(?:minutes?|mins?)": "find . -mmin -{0} -type f",
    r"(?:show|find)\s+(?:files?\s+)?(?:modified|changed)\s+(?:in\s+)?(?:the\s+)?(?:last\s+)?(\d+)\s+(?:hours?)": "find . -mmin -{0}*60 -type f",
    r"(?:show|find)\s+(?:files?\s+)?(?:modified|changed)\s+(?:in\s+)?(?:the\s+)?(?:last\s+)?(\d+)\s+(?:days?)": "find . -mtime -{0} -type f",
    r"(?:count)\s+(?:files?\s+in)\s+(\S+)": "find {0} -type f | wc -l",

    # ── Advanced Docker ──
    r"(?:show|list)\s+(?:all\s+)?(?:docker\s+)?(?:networks?)": "docker network ls",
    r"(?:show|list)\s+(?:all\s+)?(?:docker\s+)?volumes?": "docker volume ls",
    r"(?:show|check)\s+(?:docker\s+)?(?:container\s+)?(?:resource\s+)?(?:usage|stats)": "docker stats --no-stream",
    r"(?:inspect)\s+(?:docker\s+)?(?:container\s+)?(\S+)": "docker inspect {0}",
    r"(?:exec|enter|shell)\s+(?:into\s+)?(?:docker\s+)?(?:container\s+)?(\S+)": "docker exec -it {0} /bin/sh",
    r"(?:build)\s+(?:docker\s+)?image\s+(?:from\s+)?(?:dockerfile)?(?:\s+(?:tagged?|named?)\s+(\S+))?": "docker build -t {0} .",
    r"(?:push)\s+(?:docker\s+)?image\s+(\S+)": "docker push {0}",
    r"(?:pull)\s+(?:docker\s+)?image\s+(\S+)": "docker pull {0}",
    r"(?:prune|clean)\s+(?:all\s+)?(?:docker\s+)?(?:unused\s+)?(?:images?|containers?|volumes?)": "docker system prune -f",
    r"(?:show|view)\s+(?:docker\s+)?(?:compose\s+)?(?:running\s+)?(?:services?)": "docker compose ps",

    # ── Log analysis ──
    r"(?:show|tail|follow)\s+(?:the\s+)?(?:last\s+)?(\d+)\s+(?:lines?\s+)?(?:of\s+)?(?:log\s+)?(\S+)": "tail -n {0} {1}",
    r"(?:follow|watch|tail)\s+(?:log\s+)?(\S+)\s+(?:in\s+)?(?:real[- ]?time|live)": "tail -f {0}",
    r"(?:search|find|grep)\s+(?:for\s+)?(?:errors?|failures?)\s+(?:in\s+)?(\S+)": "grep -i 'error\\|fail\\|exception' {0} | tail -20",
    r"(?:count)\s+(?:errors?\s+)?(?:in\s+)?(?:log\s+)?(\S+)": "grep -ci 'error\\|fail\\|exception' {0}",
    r"(?:show|analyze)\s+(?:access\s+)?(?:log\s+)?(?:top\s+)?(?:ips?|visitors?)(?:\s+in\s+(\S+))?": "awk '{print $1}' {0} | sort | uniq -c | sort -rn | head -20",

    # ── Backup & rsync ──
    r"(?:rsync|sync)\s+(\S+)\s+(?:to\s+)?(\S+)": "rsync -avz --progress {0} {1}",
    r"(?:backup)\s+(\S+)\s+(?:to\s+)?(\S+)": "rsync -avz --progress {0} {1}",
    r"(?:mirror|clone)\s+(?:directory\s+)?(\S+)\s+(?:to\s+)?(\S+)": "rsync -avz --delete {0}/ {1}/",

    # ── Advanced git ──
    r"(?:show|find)\s+(?:who\s+)?(?:last\s+)?(?:modified|changed|edited)\s+(\S+)": "git log -1 --format='%an %ad' -- {0}",
    r"(?:show|list)\s+(?:all\s+)?(?:git\s+)?(?:conflicts?|merge\s+conflicts?)": "git diff --name-only --diff-filter=U",
    r"(?:squash|combine)\s+(?:last\s+)?(\d+)\s+commits?": "git rebase -i HEAD~{0}",
    r"(?:show|view)\s+(?:git\s+)?(?:commit\s+)?(?:graph|tree)": "git log --oneline --graph --all --decorate",
    r"(?:cherry[- ]?pick)\s+(?:commit\s+)?(\S+)": "git cherry-pick {0}",
    r"(?:show|list)\s+(?:git\s+)?stash(?:es)?": "git stash list",
    r"(?:rebase)\s+(?:onto\s+)?(\S+)": "git rebase {0}",
    r"(?:show|view)\s+(?:git\s+)?(?:file\s+)?history\s+(?:of\s+)?(\S+)": "git log --follow -p -- {0}",

    # ── Process management ──
    r"(?:show|find)\s+(?:process(?:es)?\s+)?(?:using|on)\s+port\s+(\d+)": "lsof -i :{0}",
    r"(?:show)\s+(?:top|highest)\s+(\d+)\s+(?:cpu|memory|ram)\s+(?:consuming\s+)?processes?": "ps aux --sort=-%cpu | head -n {0}",
    r"(?:run)\s+(\S+)\s+(?:in\s+)?(?:the\s+)?background": "nohup {0} &",
    r"(?:show|list)\s+(?:all\s+)?(?:background\s+)?jobs": "jobs -l",
}

# Windows-specific pattern overrides
WINDOWS_OVERRIDES = {
    # File operations
    r"(?:show|list|view)\s+(?:all\s+)?files?": "dir",
    r"(?:deep\s+)?(?:find|search|locate)\s+(?:for\s+)?(?:files?\s+)?(?:named?\s+)?(.+)": _get_deep_search_cmd('"{0}"'),
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

    # ── Security & hashing (Windows) ──
    r"(?:hash|checksum|sha256)\s+(?:of\s+)?(\S+)": "certutil -hashfile {0} SHA256",
    r"(?:md5)\s+(?:of\s+)?(\S+)": "certutil -hashfile {0} MD5",
    r"(?:check|verify)\s+(?:ssl|tls)\s+(?:cert(?:ificate)?\s+)?(?:for\s+)?(\S+)": 'powershell -NoProfile -Command "$r=[Net.HttpWebRequest]::Create(\'https://{0}\');$r.GetResponse()|Out-Null;$c=$r.ServicePoint.Certificate;$c.Subject;$c.GetExpirationDateString()"',
    r"(?:show|list)\s+(?:all\s+)?(?:installed\s+)?certificates?": 'powershell -NoProfile -Command "Get-ChildItem Cert:\\LocalMachine\\My | Format-Table Subject, NotAfter, Thumbprint"',
    r"(?:scan|check)\s+(?:open\s+)?ports?\s+(?:on\s+)?(\S+)": 'powershell -NoProfile -Command "1..1024 | ForEach-Object { $t=New-Object Net.Sockets.TcpClient; try{$t.Connect(\'{0}\',$_);Write-Host \"Port $_ open\"}catch{}finally{$t.Close()}}"',
    r"(?:show|check)\s+(?:file\s+)?(?:permissions?|perms?|acl)\s+(?:of\s+)?(\S+)": 'powershell -NoProfile -Command "Get-Acl {0} | Format-List"',
    r"(?:find)\s+(?:all\s+)?(?:world[- ]?writable|everyone)\s+files?": 'powershell -NoProfile -Command "Get-ChildItem -Recurse | Get-Acl | Where-Object {$_.AccessToString -match \"Everyone\"} | Select-Object Path"',

    # ── Event logs ──
    r"(?:show|view)\s+(?:system\s+)?(?:event\s+)?logs?": 'powershell -NoProfile -Command "Get-EventLog -LogName System -Newest 20 | Format-Table TimeGenerated, EntryType, Source, Message -Wrap"',
    r"(?:show|view)\s+(?:security\s+)?(?:event\s+)?(?:audit\s+)?logs?": 'powershell -NoProfile -Command "Get-EventLog -LogName Security -Newest 20 | Format-Table TimeGenerated, EntryType, Message -Wrap"',
    r"(?:show|find)\s+(?:failed|bad)\s+(?:login|logon)\s+attempts?": 'powershell -NoProfile -Command "Get-EventLog -LogName Security -InstanceId 4625 -Newest 20 | Format-Table TimeGenerated, Message -Wrap"',
    r"(?:show|view)\s+(?:application\s+)?error\s+logs?": 'powershell -NoProfile -Command "Get-EventLog -LogName Application -EntryType Error -Newest 20 | Format-Table TimeGenerated, Source, Message -Wrap"',

    # ── Scheduled tasks ──
    r"(?:show|list)\s+(?:all\s+)?scheduled\s+tasks?": "schtasks /query /fo TABLE",
    r"(?:show|list)\s+(?:my\s+)?(?:cron\s+)?(?:jobs|crontab|scheduled\s+tasks?)": "schtasks /query /fo TABLE",
    r"(?:create)\s+scheduled\s+task\s+(\S+)\s+(?:to\s+)?run\s+(\S+)": 'schtasks /create /tn "{0}" /tr "{1}" /sc daily',
    r"(?:delete|remove)\s+scheduled\s+task\s+(\S+)": 'schtasks /delete /tn "{0}" /f',

    # ── Registry ──
    r"(?:show|query)\s+(?:registry|reg)\s+(\S+)": "reg query {0}",

    # ── Advanced monitoring (Windows) ──
    r"(?:monitor|watch)\s+(?:cpu|system)\s+(?:usage\s+)?(?:in\s+)?(?:real[- ]?time|live)": 'powershell -NoProfile -Command "while($true){Get-Process|Sort CPU -Desc|Select -First 5 Name,CPU,@{N=''MB'';E={[math]::Round($_.WS/1MB)}};Start-Sleep 2;Clear-Host}"',
    r"(?:show|find)\s+(?:process(?:es)?\s+)?(?:using|on)\s+port\s+(\d+)": "netstat -ano | findstr :{0}",
    r"(?:show)\s+(?:top|highest)\s+(\d+)\s+(?:cpu|memory|ram)\s+(?:consuming\s+)?processes?": 'powershell -NoProfile -Command "Get-Process | Sort-Object CPU -Descending | Select-Object -First {0} Name, CPU, @{N=''RAM_MB'';E={[math]::Round($_.WorkingSet/1MB,1)}}"',
    r"(?:monitor|watch)\s+(?:disk\s+)?(?:io|i/o)\s+(?:in\s+)?(?:real[- ]?time|live)?": 'powershell -NoProfile -Command "Get-Counter ''\\PhysicalDisk(*)\\Disk Reads/sec'',''\\PhysicalDisk(*)\\Disk Writes/sec'' -SampleInterval 1 -MaxSamples 5"',
    r"(?:show|find)\s+(?:files?\s+)?(?:modified|changed)\s+(?:in\s+)?(?:the\s+)?(?:last\s+)?(\d+)\s+(?:days?)": 'powershell -NoProfile -Command "Get-ChildItem -Recurse | Where-Object {$_.LastWriteTime -gt (Get-Date).AddDays(-{0})} | Select-Object FullName, LastWriteTime"',
    r"(?:show|find)\s+(?:files?\s+)?(?:modified|changed)\s+(?:in\s+)?(?:the\s+)?(?:last\s+)?(\d+)\s+(?:hours?)": 'powershell -NoProfile -Command "Get-ChildItem -Recurse | Where-Object {$_.LastWriteTime -gt (Get-Date).AddHours(-{0})} | Select-Object FullName, LastWriteTime"',
    r"(?:count)\s+(?:files?\s+in)\s+(\S+)": 'powershell -NoProfile -Command "(Get-ChildItem -Path {0} -Recurse -File).Count"',
    r"(?:show|check)\s+(?:system\s+)?load\s+(?:average)?": 'powershell -NoProfile -Command "Get-Counter ''\\Processor(_Total)\\% Processor Time'' -SampleInterval 1 -MaxSamples 3"',
    r"(?:benchmark|test)\s+(?:disk\s+)?(?:speed|io|performance)": 'powershell -NoProfile -Command "$f=''disktest.tmp'';$sw=[Diagnostics.Stopwatch]::StartNew();[IO.File]::WriteAllBytes($f,(New-Object byte[] 104857600));$sw.Stop();$mb=100/$sw.Elapsed.TotalSeconds;Remove-Item $f;Write-Host \"Write speed: $([math]::Round($mb,1)) MB/s\""',

    # ── Windows-specific open ──
    r"(?:open)\s+(?:file\s+)?(?:explorer|manager)": "explorer .",
    r"(?:open)\s+(?:control\s+)?panel": "control",
    r"(?:open)\s+(?:device\s+)?manager": "devmgmt.msc",
    r"(?:open)\s+(?:task\s+)?manager": "taskmgr",
    r"(?:open)\s+(?:registry\s+)?editor": "regedit",
    r"(?:open)\s+(?:disk\s+)?management": "diskmgmt.msc",
}

LINUX_OVERRIDES = {
    # File operations
    r"(?:show|list|view)\s+(?:all\s+)?files?": "ls -la",
    r"(?:deep\s+)?(?:find|search|locate)\s+(?:for\s+)?(?:files?\s+)?(?:named?\s+)?(.+)": 'find . -name "*{0}*"',
    r"(?:deep\s+)?(?:search|grep|find)\s+(?:for\s+)?['\"](.+?)['\"]\s+(?:in\s+)?(?:all\s+)?files?": 'grep -rn "{0}" .',
    r"(?:show|view)\s+(?:the\s+)?(?:size|sizes)\s+(?:of\s+)?(?:all\s+)?(?:files?|folders?|directories)": "du -sh *",
    r"(?:compare|diff)\s+(\S+)\s+(?:and|with|vs)\s+(\S+)": "diff -u {0} {1}",
    r"(?:clear|cls)\s+(?:the\s+)?(?:screen|terminal|console)": "clear",

    # System
    r"(?:show|what)\s+(?:is\s+)?(?:free\s+)?(?:disk\s+)?space": "df -h",
    r"(?:show|what)\s+(?:is\s+)?memory\s+usage": "free -m",
    r"(?:find|show)\s+(?:my\s+)?(?:ip|IP)\s+(?:address)?": "ip a",
    r"(?:show|list)\s+(?:running\s+)?processes": "ps aux",
    r"(?:kill|stop)\s+process\s+(\d+)": "kill -9 {0}",
    r"(?:show|list)\s+(?:all\s+)?environment\s+variables?": "env",
    r"(?:update|upgrade)\s+(?:the\s+)?system": "sudo apt update && sudo apt upgrade -y",
    r"(?:show|view)\s+(?:system\s+)?(?:info|information)": "uname -a",
    r"(?:restart|reboot)\s+(?:the\s+)?(?:computer|system|pc|machine)": "sudo reboot",
    r"(?:shutdown|turn off|power off)\s+(?:the\s+)?(?:computer|system|pc|machine)": "sudo shutdown -h now",

    # ── Systemd services ──
    r"(?:show|list)\s+(?:all\s+)?(?:running\s+)?services?": "systemctl list-units --type=service --state=running",
    r"(?:start)\s+service\s+(\S+)": "sudo systemctl start {0}",
    r"(?:stop)\s+service\s+(\S+)": "sudo systemctl stop {0}",
    r"(?:restart)\s+service\s+(\S+)": "sudo systemctl restart {0}",
    r"(?:status|check)\s+(?:of\s+)?service\s+(\S+)": "systemctl status {0}",
    r"(?:enable)\s+service\s+(\S+)": "sudo systemctl enable {0}",
    r"(?:disable)\s+service\s+(\S+)": "sudo systemctl disable {0}",

    # ── Journal / logs ──
    r"(?:show|view)\s+(?:system\s+)?(?:logs?|journal)": "journalctl -xe --no-pager | tail -50",
    r"(?:show|view)\s+(?:logs?\s+)?(?:for\s+)?service\s+(\S+)": "journalctl -u {0} --no-pager | tail -30",
    r"(?:follow|tail)\s+(?:system\s+)?(?:logs?|journal)": "journalctl -f",

    # ── Firewall (ufw) ──
    r"(?:show|check)\s+(?:firewall|fw|ufw)\s+(?:status|rules?)": "sudo ufw status verbose",
    r"(?:allow|open)\s+(?:port\s+)?(\d+)": "sudo ufw allow {0}",
    r"(?:deny|block|close)\s+(?:port\s+)?(\d+)": "sudo ufw deny {0}",
    r"(?:enable)\s+(?:the\s+)?firewall": "sudo ufw enable",
    r"(?:disable)\s+(?:the\s+)?firewall": "sudo ufw disable",

    # ── Package managers ──
    r"(?:install)\s+(\S+)\s+(?:with|using)\s+apt": "sudo apt install -y {0}",
    r"(?:remove|uninstall)\s+(\S+)\s+(?:with|using)\s+apt": "sudo apt remove {0}",
    r"(?:search|find)\s+(\S+)\s+(?:in|on|with)\s+apt": "apt search {0}",
    r"(?:install)\s+(\S+)\s+(?:with|using)\s+(?:dnf|yum)": "sudo dnf install -y {0}",
    r"(?:install)\s+(\S+)\s+(?:with|using)\s+pacman": "sudo pacman -S {0}",

    # ── Hardware ──
    r"(?:show|check)\s+(?:cpu|processor)\s+(?:info|details?)": "lscpu",
    r"(?:show|check)\s+(?:hardware)\s+(?:info|details?)": "sudo lshw -short",
    r"(?:show|check)\s+(?:battery|power)\s+(?:status|level|info)": "upower -i /org/freedesktop/UPower/devices/battery_BAT0",

    # ── Network ──
    r"(?:show|list)\s+(?:open\s+)?(?:network\s+)?ports": "ss -tulpn",
    r"(?:flush|clear)\s+(?:dns|DNS)\s+(?:cache)?": "sudo systemd-resolve --flush-caches",
    r"(?:show|view)\s+(?:network\s+)?(?:adapters?|interfaces?)": "ip link show",

    # Virtual Env
    r"(?:activate)\s+(?:the\s+)?(?:virtual\s+)?(?:env|environment|venv)": "source .venv/bin/activate",

    # Clipboard
    r"(?:copy|save)\s+(?:output|result)\s+(?:to\s+)?clipboard": "| xclip -sel clip",
    r"(?:show|paste|view)\s+clipboard(?:\s+content)?": "xclip -sel clip -o",
}

MACOS_OVERRIDES = {
    # System
    r"(?:show|what)\s+(?:is\s+)?(?:free\s+)?(?:disk\s+)?space": "df -h",
    r"(?:show|what)\s+(?:is\s+)?memory\s+usage": "vm_stat",
    r"(?:find|show)\s+(?:my\s+)?(?:ip|IP)\s+(?:address)?": "ifconfig",
    r"(?:update|upgrade)\s+(?:the\s+)?system": "brew update && brew upgrade",
    r"(?:show|view)\s+(?:system\s+)?(?:info|information)": "system_profiler SPSoftwareDataType",
    r"(?:restart|reboot)\s+(?:the\s+)?(?:computer|system|pc|machine)": "sudo shutdown -r now",
    r"(?:shutdown|turn off|power off)\s+(?:the\s+)?(?:computer|system|pc|machine)": "sudo shutdown -h now",

    # ── Homebrew ──
    r"(?:install)\s+(\S+)\s+(?:with|using)\s+(?:brew|homebrew)": "brew install {0}",
    r"(?:remove|uninstall)\s+(\S+)\s+(?:with|using)\s+(?:brew|homebrew)": "brew uninstall {0}",
    r"(?:search|find)\s+(\S+)\s+(?:in|on|with)\s+(?:brew|homebrew)": "brew search {0}",
    r"(?:list|show)\s+(?:installed\s+)?(?:brew|homebrew)\s+packages?": "brew list",
    r"(?:show|list)\s+(?:outdated|upgradable)\s+(?:brew\s+)?packages?": "brew outdated",
    r"(?:cleanup)\s+(?:brew|homebrew)": "brew cleanup",

    # ── Services (launchctl) ──
    r"(?:show|list)\s+(?:all\s+)?(?:running\s+)?services?": "launchctl list",
    r"(?:start)\s+service\s+(\S+)": "launchctl start {0}",
    r"(?:stop)\s+service\s+(\S+)": "launchctl stop {0}",

    # ── Hardware & battery ──
    r"(?:show|check)\s+(?:cpu|processor)\s+(?:info|details?)": "sysctl -n machdep.cpu.brand_string",
    r"(?:show|check)\s+(?:hardware)\s+(?:info|details?)": "system_profiler SPHardwareDataType",
    r"(?:show|check)\s+(?:battery|power)\s+(?:status|level|info)": "pmset -g batt",
    r"(?:show|check)\s+(?:usb)\s+(?:devices?)": "system_profiler SPUSBDataType",

    # ── Network ──
    r"(?:show|list)\s+(?:open\s+)?(?:network\s+)?ports": "lsof -i -P -n | grep LISTEN",
    r"(?:show|view)\s+(?:network\s+)?(?:adapters?|interfaces?)": "ifconfig",
    r"(?:show|list)\s+(?:all\s+)?(?:saved\s+)?wifi(?:s)?\s+(?:networks?|profiles?)": "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -s",

    # ── Spotlight search ──
    r"(?:deep\s+)?(?:find|search|locate)\s+(?:for\s+)?(?:files?\s+)?(?:named?\s+)?(.+)": 'mdfind -name "{0}"',

    # ── Open/launch ──
    r"(?:open)\s+(?:finder|file\s+manager)": "open .",
    r"(?:open)\s+(\S+)\s+(?:in|with)\s+(\S+)": "open -a {1} {0}",

    # DNS
    r"(?:flush|clear)\s+(?:dns|DNS)\s+(?:cache)?": "sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder",

    # ── Firewall ──
    r"(?:show|check)\s+(?:firewall|fw)\s+(?:status|rules?)": "sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate",
    r"(?:enable)\s+(?:the\s+)?firewall": "sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on",
    r"(?:disable)\s+(?:the\s+)?firewall": "sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off",

    # Virtual Env
    r"(?:activate)\s+(?:the\s+)?(?:virtual\s+)?(?:env|environment|venv)": "source .venv/bin/activate",

    # Clipboard
    r"(?:copy|save)\s+(?:output|result)\s+(?:to\s+)?clipboard": "| pbcopy",
    r"(?:show|paste|view)\s+clipboard(?:\s+content)?": "pbpaste",

    # ── Screen & display ──
    r"(?:take\s+(?:a\s+)?)?screenshot": "screencapture ~/Desktop/screenshot.png",
    r"(?:show|check)\s+(?:screen\s+)?resolution": "system_profiler SPDisplaysDataType | grep Resolution",
    r"(?:lock)\s+(?:the\s+)?(?:screen|computer)": "pmset displaysleepnow",

    # ── Disk ──
    r"(?:show|list)\s+(?:all\s+)?(?:drives?|disks?|volumes?)": "diskutil list",
    r"(?:eject)\s+(\S+)": "diskutil eject {0}",
    r"(?:empty|clear)\s+(?:the\s+)?(?:trash|bin)": "rm -rf ~/.Trash/*",
}


# ═══════════════════════════════════════════════════════════
# Translator — Production Engine
# ═══════════════════════════════════════════════════════════

class Translator:
    """
    Production-grade NL → command translator.

    Features:
    - Local pattern matching for common commands (~250+ patterns)
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
        self.swarm = None  # Lazy-loaded swarm orchestrator
        self._phrase_dict = None  # Lazy-loaded 2500+ offline phrase dictionary

    def translate(self, user_input: str, entities: Optional[dict[str, Any]] = None) -> TranslationResult:
        """
        Translate natural language to shell command(s).

        Pipeline:
        1. Check feedback corrections
        2. Check history cache
        3. Try local pattern matching
        3.5. Try 2554+ offline phrase dictionary
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
        smart = self._try_smart_open(user_input_clean)
        if smart:
            return smart

        # 3. Try local pattern matching
        local = self._try_local_patterns(user_input_clean)
        if local:
            return local

        # 3.5. Try 2554+ Offline Phrase Dictionary (TF-IDF Cosine Matcher)
        phrase_match = self._try_phrase_dictionary(user_input_clean)
        if phrase_match:
            return phrase_match

        # 4. Multi-step detection
        if self._is_multi_step(user_input_clean):
            return self._translate_multi_step(user_input_clean, entities)

        # 5. LLM translation
        return self._llm_translate(user_input_clean, entities)

    def _try_phrase_dictionary(self, user_input: str) -> Optional[TranslationResult]:
        """Query the 2,554+ offline phrase TF-IDF vector index (<0.5ms)."""
        try:
            if not self._phrase_dict:
                from intelligence.phrase_dictionary import PhraseDictionary
                self._phrase_dict = PhraseDictionary()
                self._phrase_dict.load()

            match = self._phrase_dict.translate(user_input, threshold=0.45)
            if match and match.get("command"):
                return TranslationResult(
                    command=match["command"],
                    confidence=float(match.get("confidence", 0.88)),
                    explanation=f"Matched offline phrase: '{match.get('english', '')}'",
                    source="offline-dictionary",
                    provenance=ProvenanceTag(
                        source=ProvenanceSource.LOCAL,
                        confidence=float(match.get("confidence", 0.88)),
                        detail="2500+ offline phrase dictionary",
                        latency_ms=0.5,
                    ),
                )
        except Exception:
            pass
        return None

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

    def _get_smart_open_engine(self) -> Optional[Any]:
        """Lazy-load SmartOpenEngine when path or app resolution is needed."""
        if self._smart_open is None:
            try:
                from intelligence.smart_open import SmartOpenEngine
                self._smart_open = SmartOpenEngine()
            except ImportError:
                return None
        return self._smart_open

    def _try_smart_open(self, user_input: str) -> Optional[TranslationResult]:
        """Attempt to route through the SmartOpen Engine for URLs, apps, drives, and power commands."""
        engine = self._get_smart_open_engine()
        if engine is None:
            return None

        result = engine.try_resolve(user_input)
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
        os_name = plat.system()

        # Compile patterns. LOCAL_PATTERNS first, then OS_OVERRIDES so overrides take precedence
        patterns = {}
        patterns.update(LOCAL_PATTERNS)
        if os_name == "Windows":
            patterns.update(WINDOWS_OVERRIDES)
        elif os_name == "Linux":
            patterns.update(LINUX_OVERRIDES)
        elif os_name == "Darwin":
            patterns.update(MACOS_OVERRIDES)

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

        is_windows = os_name == "Windows"
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
            (r"(?:make|create)\s+(?:a\s+)?(?:directory|folder|dir)\s+(?:(?:called|name|named)\s+)?(\S+)", lambda g: self._build_cmd(["mkdir", g[0]])),
            (r"(?:delete|remove)\s+(?:the\s+)?(?:file|directory|folder)\s+(\S+)", lambda g: self._build_cmd(["rm", g[0]])),
            # Windows folder copy / move with well-known source and destination roots.
            # Accept both "from desktop folder to downloads folder" and
            # "from desktop to downloads folder" phrasing.
            (r"(?:create|make)\s+(?:a\s+|an\s+)?(?:copy|backup)\s+of\s+(?:the\s+)?(.+?)\s+(?:folder|directory)\s+from\s+(?:the\s+)?(.+?)(?:\s+(?:folder|directory))?\s+(?:to|into)\s+(?:the\s+)?(.+?)(?:\s+(?:folder|directory))?\s*$", lambda g: self._build_windows_folder_copy_command(g[0].strip(), g[1].strip(), g[2].strip()) if is_windows else None),
            (r"(?:copy|backup)\s+(?:the\s+)?(.+?)\s+(?:folder|directory)\s+from\s+(?:the\s+)?(.+?)(?:\s+(?:folder|directory))?\s+(?:to|into)\s+(?:the\s+)?(.+?)(?:\s+(?:folder|directory))?\s*$", lambda g: self._build_windows_folder_copy_command(g[0].strip(), g[1].strip(), g[2].strip()) if is_windows else None),
            (r"(?:move|transfer)\s+(?:the\s+)?(.+?)\s+(?:folder|directory)\s+from\s+(?:the\s+)?(.+?)(?:\s+(?:folder|directory))?\s+(?:to|into)\s+(?:the\s+)?(.+?)(?:\s+(?:folder|directory))?\s*$", lambda g: self._build_windows_folder_move_command(g[0].strip(), g[1].strip(), g[2].strip()) if is_windows else None),
            # Folder copy / backup — "create a copy of X folder in Y", "backup X to Y", "copy X folder to Y"
            (r"(?:create\s+(?:a\s+|an\s+)?(?:copy|backup)\s+of\s+(?:the\s+)?(.+?)\s+(?:folder\s+)?(?:in|to|into)\s+(?:the\s+)?(.+?)(?:\s+folder)?)\s*$", lambda g: self._build_cmd(["robocopy", g[0].strip(), g[1].strip(), "/E", "/DCOPY:T"]) if is_windows else self._build_cmd(["cp", "-r", g[0].strip(), g[1].strip()])),
            (r"(?:copy|backup)\s+(?:the\s+)?(.+?)\s+(?:folder|directory)\s+(?:in|to|into)\s+(?:the\s+)?(.+?)(?:\s+(?:folder|directory))?\s*$", lambda g: self._build_cmd(["robocopy", g[0].strip(), g[1].strip(), "/E", "/DCOPY:T"]) if is_windows else self._build_cmd(["cp", "-r", g[0].strip(), g[1].strip()])),
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

    def _build_windows_folder_copy_command(self, source_name: str, source_base: str, dest_base: str) -> Optional[str]:
        """Build a safe Windows folder copy command for resolved source/destination roots."""
        return self._build_windows_folder_transfer_command(source_name, source_base, dest_base, move=False)

    def _build_windows_folder_move_command(self, source_name: str, source_base: str, dest_base: str) -> Optional[str]:
        """Build a safe Windows folder move command for resolved source/destination roots."""
        return self._build_windows_folder_transfer_command(source_name, source_base, dest_base, move=True)

    def _build_windows_folder_transfer_command(self, source_name: str, source_base: str, dest_base: str, move: bool = False) -> Optional[str]:
        """Resolve well-known folder roots and generate a quoted PowerShell copy/move command."""
        engine = self._get_smart_open_engine()
        if engine is None:
            return None

        source_root = engine._resolve_folder(source_base)
        dest_root = engine._resolve_folder(dest_base)
        if not source_root or not dest_root:
            return None

        cleaned_name = re.sub(r'\s+(?:folder|directory|dir)$', '', source_name.strip(), flags=re.IGNORECASE)
        source_path = engine._search_dir_for(source_root, cleaned_name.lower())
        if not source_path:
            candidate = os.path.join(source_root, cleaned_name)
            if os.path.isdir(candidate):
                source_path = candidate
            else:
                source_path = engine._fuzzy_find_folder(cleaned_name.lower(), search_root=source_root)

        if not source_path:
            return None

        verb = "Move-Item" if move else "Copy-Item"
        source_literal = self._powershell_literal(source_path)
        dest_literal = self._powershell_literal(os.path.abspath(dest_root))
        extra_args = "-Force" if move else "-Recurse -Force"
        return self._build_cmd([
            "powershell",
            "-NoProfile",
            "-Command",
            f"{verb} -LiteralPath {source_literal} -Destination {dest_literal} {extra_args}",
        ])

    @staticmethod
    def _powershell_literal(value: str) -> str:
        """Quote a PowerShell literal string using single-quote escaping."""
        return "'" + value.replace("'", "''") + "'"

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
        
        if self.swarm is None:
            try:
                from neuroshell.intelligence.swarm import SwarmOrchestrator
                self.swarm = SwarmOrchestrator(self.llm, self.context)
            except Exception:
                pass

        if self.swarm is None:
            return self._llm_translate(user_input, self.context)

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
