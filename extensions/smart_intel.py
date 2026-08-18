# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Live Command Explainer + Risk Scoring + Project Context
Tier 1+3: Real-time command explanation, risk visualization, and project detection.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("neuroshell.intelligence")

# ═══════════════════════════════════════════════════════════
# Live Command Explainer
# ═══════════════════════════════════════════════════════════

COMMAND_KNOWLEDGE = {
    "chmod": {
        "desc": "Change file permissions",
        "perms": {"0": "---", "1": "--x", "2": "-w-", "3": "-wx", "4": "r--", "5": "r-x", "6": "rw-", "7": "rwx"},
        "positions": ["Owner", "Group", "Others"],
        "flags": {"-R": "Recursive (apply to all files/dirs inside)", "+x": "Add execute permission"},
    },
    "chown": {"desc": "Change file owner/group", "flags": {"-R": "Recursive"}},
    "rm": {
        "desc": "Remove files/directories",
        "flags": {"-r": "Recursive (delete directories)", "-f": "Force (no confirmation)", "-i": "Interactive (ask before each)", "-rf": "⚠️ Force delete everything recursively"},
    },
    "dd": {"desc": "Low-level data copy/conversion", "flags": {"if=": "Input file", "of=": "Output file", "bs=": "Block size", "count=": "Number of blocks"}},
    "tar": {
        "desc": "Archive utility",
        "flags": {"-c": "Create archive", "-x": "Extract archive", "-z": "Gzip compress", "-j": "Bzip2 compress", "-f": "Specify filename", "-v": "Verbose output"},
    },
    "grep": {"desc": "Search text patterns", "flags": {"-r": "Recursive search", "-i": "Case insensitive", "-n": "Show line numbers", "-l": "Show filenames only", "-c": "Count matches", "-v": "Invert match"}},
    "find": {"desc": "Search for files", "flags": {"-name": "Match filename", "-type": "File type (f=file, d=dir)", "-size": "File size", "-mtime": "Modified time (days)", "-exec": "Execute command on results"}},
    "curl": {"desc": "Transfer data from URLs", "flags": {"-O": "Save with original name", "-o": "Save to file", "-X": "HTTP method", "-H": "Header", "-d": "POST data", "-k": "Skip SSL verify"}},
    "ssh": {"desc": "Secure shell remote login", "flags": {"-p": "Port number", "-i": "Identity key file", "-L": "Local port forward", "-R": "Remote port forward"}},
    "rsync": {"desc": "Remote/local file sync", "flags": {"-a": "Archive mode", "-v": "Verbose", "-z": "Compress during transfer", "--delete": "Delete files not in source", "--progress": "Show progress"}},
    "docker": {
        "desc": "Container management",
        "subcommands": {"run": "Create and start container", "build": "Build image from Dockerfile", "ps": "List containers", "stop": "Stop container", "exec": "Run command in container",
                        "logs": "View container logs", "pull": "Download image", "push": "Upload image", "images": "List images", "network": "Manage networks", "volume": "Manage volumes",
                        "compose": "Multi-container orchestration", "system prune": "Clean unused resources"},
    },
    "git": {
        "desc": "Version control",
        "subcommands": {"rebase -i": "Interactive rebase (squash/edit commits)", "cherry-pick": "Apply specific commit to current branch", "bisect": "Binary search for bug-introducing commit",
                        "reflog": "Reference log (undo almost anything)", "stash": "Temporarily save changes", "reset --hard": "⚠️ Discard all changes permanently"},
    },
    "kubectl": {
        "desc": "Kubernetes cluster management",
        "subcommands": {"get": "List resources", "describe": "Show details", "apply": "Apply config", "delete": "Remove resource", "logs": "View pod logs", "exec": "Run command in pod", "scale": "Change replica count"},
    },
    "iptables": {"desc": "Linux firewall rules", "flags": {"-A": "Append rule", "-D": "Delete rule", "-L": "List rules", "-F": "Flush all rules", "-P": "Set default policy"}},
    "systemctl": {"desc": "Systemd service manager", "subcommands": {"start": "Start service", "stop": "Stop service", "restart": "Restart service", "enable": "Auto-start on boot", "status": "Check service status"}},
    "netstat": {"desc": "Network statistics", "flags": {"-t": "TCP connections", "-u": "UDP", "-l": "Listening only", "-p": "Show process", "-n": "Numeric addresses", "-a": "All connections"}},
    "nmap": {"desc": "Network port scanner", "flags": {"-sT": "TCP connect scan", "-sS": "SYN stealth scan", "-sU": "UDP scan", "-O": "OS detection", "-A": "Aggressive scan", "-p": "Port range"}},
}


def explain_command(command: str) -> dict | None:
    """Explain a command in real-time as the user types."""
    parts = command.strip().split()
    if not parts:
        return None

    base_cmd = parts[0]
    info = COMMAND_KNOWLEDGE.get(base_cmd)
    if not info:
        return None

    result = {"command": base_cmd, "description": info["desc"], "details": []}

    # chmod special handling
    if base_cmd == "chmod" and len(parts) >= 2:
        perm_str = parts[1]
        if re.match(r"^\d{3}$", perm_str):
            perms = info["perms"]
            positions = info["positions"]
            for i, digit in enumerate(perm_str):
                perm_text = perms.get(digit, "???")
                result["details"].append(f"{positions[i]}: {perm_text} ({digit})")

    # Flag explanations
    flags = info.get("flags", {})
    for part in parts[1:]:
        for flag, desc in flags.items():
            if part.startswith(flag):
                result["details"].append(f"{flag} → {desc}")

    # Subcommand explanations
    subcmds = info.get("subcommands", {})
    if len(parts) >= 2:
        sub = parts[1]
        full_sub = f"{parts[1]} {parts[2]}" if len(parts) >= 3 else ""
        if full_sub in subcmds:
            result["details"].append(f"{full_sub} → {subcmds[full_sub]}")
        elif sub in subcmds:
            result["details"].append(f"{sub} → {subcmds[sub]}")

    return result if result["details"] else result


# ═══════════════════════════════════════════════════════════
# Command Risk Scoring
# ═══════════════════════════════════════════════════════════

RISK_PATTERNS = [
    (10, [r"rm\s+-rf\s+/\s*$", r"mkfs\.", r"dd\s+.*of=/dev/sd", r":\(\)\{.*\}", r"chmod\s+-R\s+777\s+/"]),
    (9, [r"rm\s+-rf\s+~", r"drop\s+database", r"truncate\s+table", r"format\s+[a-z]:", r"del\s+/s\s+/q\s+c:\\"]),
    (8, [r"sudo\s+rm\s+-rf", r"git\s+reset\s+--hard", r"git\s+push\s+.*--force", r"docker\s+system\s+prune", r"shutdown", r"reboot"]),
    (7, [r"curl\s+.*\|\s*(?:bash|sh)", r"wget\s+.*\|\s*(?:bash|sh)", r"pip\s+install\s+--user", r"npm\s+install\s+-g"]),
    (6, [r"kill\s+-9", r"pkill", r"taskkill\s+/f", r"iptables\s+-F", r"ufw\s+disable"]),
    (5, [r"sudo\s+", r"runas\s+", r"chmod\s+777", r"docker\s+exec", r"kubectl\s+delete"]),
    (3, [r"git\s+push", r"docker\s+stop", r"pip\s+uninstall", r"npm\s+uninstall", r"apt\s+remove"]),
    (1, [r"ls", r"cat", r"echo", r"pwd", r"whoami", r"date", r"git\s+status", r"git\s+log", r"docker\s+ps"]),
]


@dataclass
class RiskAssessment:
    score: int  # 0-10
    level: str  # safe, low, medium, high, critical
    reasons: list[str]
    badge: str

    @property
    def meter(self) -> str:
        filled = self.score
        empty = 10 - filled
        colors = {0: "🟢", 1: "🟢", 2: "🟢", 3: "🟡", 4: "🟡", 5: "🟡", 6: "🟠", 7: "🟠", 8: "🔴", 9: "🔴", 10: "🔴"}
        bar = colors.get(self.score, "⚪") * filled + "⚪" * empty
        return f"[{bar}] {self.score}/10"


def score_risk(command: str) -> RiskAssessment:
    """Score command risk from 0 (safe) to 10 (catastrophic)."""
    max_score = 0
    reasons = []
    cmd_lower = command.lower().strip()

    for score, patterns in RISK_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, cmd_lower):
                if score > max_score:
                    max_score = score
                reasons.append(f"Matched: {pattern[:40]}")

    levels = {0: "safe", 1: "safe", 2: "low", 3: "low", 4: "medium", 5: "medium", 6: "high", 7: "high", 8: "critical", 9: "critical", 10: "critical"}
    badges = {0: "✅ SAFE", 1: "✅ SAFE", 2: "🟢 LOW", 3: "🟡 LOW", 4: "🟡 MEDIUM", 5: "🟠 MEDIUM", 6: "🟠 HIGH", 7: "🔴 HIGH", 8: "🔴 CRITICAL", 9: "🔴 CRITICAL", 10: "💀 CATASTROPHIC"}

    return RiskAssessment(
        score=max_score,
        level=levels.get(max_score, "unknown"),
        reasons=reasons[:3],
        badge=badges.get(max_score, "❓"),
    )


# ═══════════════════════════════════════════════════════════
# Project Context Awareness
# ═══════════════════════════════════════════════════════════

PROJECT_SIGNATURES = {
    "django": {"files": ["manage.py", "settings.py"], "dirs": [], "commands": {"run": "python manage.py runserver", "test": "python manage.py test", "migrate": "python manage.py migrate", "shell": "python manage.py shell"}},
    "flask": {"files": ["app.py", "wsgi.py"], "dirs": [], "commands": {"run": "flask run", "test": "python -m pytest", "shell": "flask shell"}},
    "fastapi": {"files": ["main.py"], "dirs": [], "pip_marker": "fastapi", "commands": {"run": "uvicorn main:app --reload", "test": "python -m pytest"}},
    "react": {"files": ["package.json"], "dirs": ["src", "public"], "npm_marker": "react", "commands": {"run": "npm start", "test": "npm test", "build": "npm run build"}},
    "nextjs": {"files": ["next.config.js", "next.config.mjs"], "dirs": ["pages", "app"], "commands": {"run": "npm run dev", "build": "npm run build", "start": "npm start"}},
    "vue": {"files": ["vue.config.js"], "dirs": ["src"], "npm_marker": "vue", "commands": {"run": "npm run serve", "build": "npm run build"}},
    "rust": {"files": ["Cargo.toml"], "dirs": ["src"], "commands": {"run": "cargo run", "test": "cargo test", "build": "cargo build --release"}},
    "go": {"files": ["go.mod"], "dirs": [], "commands": {"run": "go run .", "test": "go test ./...", "build": "go build"}},
    "node": {"files": ["package.json"], "dirs": ["node_modules"], "commands": {"run": "npm start", "test": "npm test", "build": "npm run build"}},
    "python": {"files": ["requirements.txt", "setup.py", "pyproject.toml"], "dirs": [], "commands": {"run": "python main.py", "test": "python -m pytest", "install": "pip install -r requirements.txt"}},
    "docker": {"files": ["Dockerfile", "docker-compose.yml"], "dirs": [], "commands": {"run": "docker compose up -d", "build": "docker compose build", "down": "docker compose down", "logs": "docker compose logs -f"}},
    "terraform": {"files": ["main.tf"], "dirs": [".terraform"], "commands": {"run": "terraform plan", "apply": "terraform apply", "init": "terraform init"}},
    "k8s": {"files": [], "dirs": ["k8s", "kubernetes", "manifests"], "commands": {"apply": "kubectl apply -f k8s/", "status": "kubectl get pods", "logs": "kubectl logs -f"}},
}


@dataclass
class ProjectInfo:
    project_type: str
    confidence: float
    commands: dict
    detected_files: list[str]


def detect_project(cwd: str = ".") -> ProjectInfo | None:
    """Detect project type from current directory."""
    cwd_path = Path(cwd).resolve()
    best_match = None
    best_score = 0

    for proj_type, sig in PROJECT_SIGNATURES.items():
        score = 0
        detected = []

        for f in sig["files"]:
            if (cwd_path / f).exists():
                score += 2
                detected.append(f)

        for d in sig.get("dirs", []):
            if (cwd_path / d).is_dir():
                score += 1
                detected.append(f"{d}/")

        # Check package.json for npm markers
        if "npm_marker" in sig and (cwd_path / "package.json").exists():
            try:
                pkg = __import__("json").loads((cwd_path / "package.json").read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if sig["npm_marker"] in deps:
                    score += 3
            except Exception:
                pass

        if score > best_score:
            best_score = score
            best_match = ProjectInfo(
                project_type=proj_type,
                confidence=min(score / 5.0, 1.0),
                commands=sig["commands"],
                detected_files=detected,
            )

    return best_match if best_match and best_score >= 2 else None
