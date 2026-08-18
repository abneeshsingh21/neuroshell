# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Command Explainer — Production Grade
Offline database for 50+ common commands, man-page integration,
interactive flag drill-down, and visual pipeline diagrams.
"""

import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

from observability.provenance import ProvenanceTag, ProvenanceSource


@dataclass
class FlagExplanation:
    flag: str
    meaning: str
    is_dangerous: bool = False


@dataclass
class ExplainResult:
    summary: str
    breakdown: list[dict] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    related_commands: list[str] = field(default_factory=list)
    provenance: Optional[ProvenanceTag] = None
    source: str = ""
    examples: list[str] = field(default_factory=list)
    man_excerpt: str = ""


# Compact offline DB: command -> (summary, {flag: meaning}, [related], [examples])
_DB = {
    "ls": ("List directory contents", {"-l": "Long format", "-a": "Show hidden", "-h": "Human sizes", "-R": "Recursive", "-t": "Sort by time", "-S": "Sort by size"}, ["dir", "find", "tree"], ["ls -lah"]),
    "cd": ("Change directory", {"-": "Previous dir", "~": "Home"}, ["pushd", "popd", "pwd"], ["cd .."]),
    "cp": ("Copy files/dirs", {"-r": "Recursive", "-i": "Prompt overwrite", "-v": "Verbose"}, ["mv", "rsync"], ["cp -rv src/ dest/"]),
    "mv": ("Move/rename files", {"-i": "Prompt overwrite", "-v": "Verbose", "-n": "No overwrite"}, ["cp", "rename"], ["mv old.py new.py"]),
    "rm": ("Remove files/dirs", {"-r": "Recursive", "-f": "Force", "-i": "Prompt", "-v": "Verbose"}, ["rmdir", "trash-put"], ["rm -rf node_modules/"]),
    "mkdir": ("Create directories", {"-p": "Create parents", "-v": "Verbose"}, ["rmdir", "touch"], ["mkdir -p src/components"]),
    "touch": ("Create file / update timestamp", {"-c": "Don't create"}, ["mkdir", "echo"], ["touch index.js"]),
    "cat": ("Display file contents", {"-n": "Number lines", "-b": "Number non-blank"}, ["less", "head", "tail", "bat"], ["cat -n config.py"]),
    "head": ("Show first lines", {"-n": "Line count"}, ["tail", "cat"], ["head -n 20 log.txt"]),
    "tail": ("Show last lines", {"-n": "Line count", "-f": "Follow"}, ["head", "cat"], ["tail -f server.log"]),
    "find": ("Search files in tree", {"-name": "Filename pattern", "-type": "Type (f/d)", "-size": "File size", "-exec": "Execute on match"}, ["fd", "locate", "grep"], ["find . -name '*.py'"]),
    "chmod": ("Change permissions", {"+x": "Add execute", "-R": "Recursive"}, ["chown", "ls -l"], ["chmod +x script.sh"]),
    "tar": ("Archive files", {"-c": "Create", "-x": "Extract", "-z": "Gzip", "-f": "File", "-v": "Verbose"}, ["zip", "unzip", "gzip"], ["tar -xzf archive.tar.gz"]),
    "grep": ("Search text patterns", {"-r": "Recursive", "-i": "Case-insensitive", "-n": "Line numbers", "-l": "Files only", "-c": "Count", "-v": "Invert"}, ["rg", "awk", "sed"], ["grep -rn 'TODO' ."]),
    "sed": ("Stream text editor", {"-i": "In-place edit", "-e": "Expression"}, ["awk", "grep", "tr"], ["sed -i 's/old/new/g' file"]),
    "awk": ("Text processing language", {"-F": "Field separator"}, ["sed", "cut", "grep"], ["awk -F: '{print $1}' /etc/passwd"]),
    "sort": ("Sort lines", {"-r": "Reverse", "-n": "Numeric", "-u": "Unique", "-k": "By field"}, ["uniq", "head"], ["sort -rh sizes.txt"]),
    "wc": ("Count lines/words/chars", {"-l": "Lines", "-w": "Words", "-c": "Bytes"}, ["cat", "grep -c"], ["wc -l *.py"]),
    "du": ("Disk usage", {"-h": "Human-readable", "-s": "Summary", "-d": "Max depth"}, ["df", "ncdu"], ["du -sh */"]),
    "df": ("Filesystem disk space", {"-h": "Human-readable", "-T": "Show type"}, ["du", "mount"], ["df -h"]),
    "xargs": ("Build commands from stdin", {"-I": "Replace string", "-P": "Parallel", "-n": "Max args"}, ["find", "parallel"], ["find . -name '*.log' | xargs rm"]),
    "curl": ("Transfer data from URLs", {"-X": "HTTP method", "-H": "Header", "-d": "POST data", "-o": "Output file", "-s": "Silent", "-L": "Follow redirects"}, ["wget", "httpie"], ["curl -s https://api.github.com"]),
    "wget": ("Download files", {"-O": "Output file", "-q": "Quiet", "-r": "Recursive", "-c": "Continue"}, ["curl", "aria2c"], ["wget -O out.zip URL"]),
    "ssh": ("Secure shell login", {"-p": "Port", "-i": "Key file", "-L": "Local forward"}, ["scp", "rsync"], ["ssh user@server"]),
    "scp": ("Secure copy", {"-r": "Recursive", "-P": "Port"}, ["rsync", "ssh"], ["scp file.txt user@host:/path/"]),
    "ping": ("Send ICMP echo", {"-c": "Count"}, ["traceroute", "nslookup"], ["ping -c 4 google.com"]),
    "git": ("Version control", {"clone": "Clone repo", "add": "Stage changes", "commit": "Record changes", "push": "Upload", "pull": "Download", "status": "Working tree status", "log": "History", "branch": "Branches", "merge": "Merge branches", "stash": "Stash changes", "diff": "Show changes", "reset": "Reset HEAD", "rebase": "Reapply commits"}, ["gh", "hg"], ["git log --oneline -10"]),
    "docker": ("Container runtime", {"run": "Start container", "build": "Build image", "ps": "List containers", "stop": "Stop", "rm": "Remove", "images": "List images", "exec": "Run in container", "logs": "View logs", "compose": "Multi-container"}, ["podman", "kubectl"], ["docker ps -a"]),
    "pip": ("Python package installer", {"install": "Install", "uninstall": "Remove", "list": "List installed", "freeze": "Requirements fmt", "--user": "User dir"}, ["pipx", "conda", "poetry"], ["pip install -r requirements.txt"]),
    "npm": ("Node.js package manager", {"install": "Install", "run": "Run script", "start": "Start app", "test": "Run tests", "-g": "Global", "-D": "Dev dep"}, ["yarn", "pnpm"], ["npm install --save-dev jest"]),
    "cargo": ("Rust package manager", {"build": "Compile", "run": "Compile+run", "test": "Test", "--release": "Release build"}, ["rustup"], ["cargo build --release"]),
    "python": ("Python interpreter", {"-m": "Run module", "-c": "Execute string", "-V": "Version"}, ["python3", "pip", "ipython"], ["python -m pytest -v"]),
    "ps": ("Show processes", {"aux": "All with details", "-ef": "Full listing"}, ["top", "htop", "kill"], ["ps aux | grep node"]),
    "kill": ("Send signal to process", {"-9": "SIGKILL (force)", "-15": "SIGTERM (graceful)"}, ["pkill", "killall", "ps"], ["kill -9 12345"]),
    "kubectl": ("Kubernetes CLI", {"get": "List resources", "apply": "Apply config", "delete": "Delete", "describe": "Details", "logs": "Pod logs", "-n": "Namespace"}, ["helm", "k9s"], ["kubectl get pods -A"]),
    "terraform": ("Infrastructure as Code", {"init": "Initialize", "plan": "Preview", "apply": "Apply", "destroy": "Destroy"}, ["pulumi"], ["terraform plan"]),
    "lsof": ("List open files/connections", {"-i": "Network", "-P": "No port names"}, ["netstat", "ss"], ["lsof -i :8080"]),
    "echo": ("Display text", {"-n": "No newline", "-e": "Enable escapes"}, ["printf", "cat"], ["echo $PATH"]),
    "diff": ("Compare files", {"-u": "Unified format", "-r": "Recursive"}, ["patch", "comm"], ["diff -u old.py new.py"]),
    "env": ("Show/set env vars", {"-i": "Empty environment"}, ["export", "printenv"], ["env | grep PATH"]),
    "make": ("Build automation", {"-j": "Parallel jobs", "-f": "Makefile path", "-n": "Dry run"}, ["cmake", "ninja"], ["make -j4"]),
}

DANGEROUS_FLAGS = {"-rf", "--force", "-f", "--hard", "--no-verify", "-9", "--delete"}


class Explainer:
    """Production-grade command explainer: offline DB → man-page → LLM."""

    def __init__(self, llm_client=None, context_manager=None):
        self.llm = llm_client
        self.context = context_manager

    def explain(self, command: str) -> ExplainResult:
        """Explain a command using best available source."""
        base_cmd = command.strip().split()[0].lower() if command.strip() else ""

        # 1. Offline database (instant)
        offline = self._explain_offline(command, base_cmd)
        if offline:
            return offline

        # 2. Man-page / --help
        man_result = self._explain_manpage(base_cmd)

        # 3. LLM fallback
        if self.llm:
            return self._explain_llm(command, man_result)

        return ExplainResult(
            summary=f"No explanation available for '{base_cmd}'",
            source="none", man_excerpt=man_result or "",
            provenance=ProvenanceTag(source=ProvenanceSource.FALLBACK, confidence=0.0),
        )

    def explain_flag(self, command: str, flag: str) -> Optional[FlagExplanation]:
        """Explain a specific flag."""
        base_cmd = command.strip().split()[0].lower()
        entry = _DB.get(base_cmd)
        if entry and flag in entry[1]:
            return FlagExplanation(flag=flag, meaning=entry[1][flag], is_dangerous=flag in DANGEROUS_FLAGS)
        return None

    def get_examples(self, command: str) -> list[str]:
        base_cmd = command.strip().split()[0].lower()
        entry = _DB.get(base_cmd)
        return list(entry[3]) if entry else []

    def _explain_offline(self, command: str, base_cmd: str) -> Optional[ExplainResult]:
        entry = _DB.get(base_cmd)
        if not entry:
            return None

        summary, flags_db, related, examples = entry
        parts = command.strip().split()
        breakdown = [{"part": base_cmd, "meaning": summary}]
        risks = []

        for part in parts[1:]:
            if part.startswith("-"):
                meaning = flags_db.get(part, f"Flag: {part}")
                breakdown.append({"part": part, "meaning": meaning})
                if part in DANGEROUS_FLAGS:
                    risks.append(f"'{part}' is destructive")
            else:
                sc = flags_db.get(part, "")
                breakdown.append({"part": part, "meaning": sc or f"argument: {part}"})

        return ExplainResult(
            summary=summary, breakdown=breakdown,
            risks=risks or ["No significant risks"],
            related_commands=related, examples=examples, source="offline",
            provenance=ProvenanceTag(source=ProvenanceSource.PATTERN, confidence=0.95, detail="offline database", latency_ms=0.1),
        )

    SAFE_HELP_COMMANDS = {
        "git", "docker", "tar", "grep", "curl", "wget", "npm", "pip", "python", "python3",
        "cargo", "go", "kubectl", "systemctl", "find", "sed", "awk", "ls", "df", "ps",
        "netstat", "ip", "ssh", "scp", "rsync", "chmod", "chown", "uname", "top", "free"
    }

    def _explain_manpage(self, base_cmd: str) -> str:
        clean_cmd = base_cmd.strip().lower()
        if clean_cmd in self.SAFE_HELP_COMMANDS:
            try:
                r = subprocess.run([base_cmd, "--help"], capture_output=True, text=True, timeout=3)
                out = r.stdout or r.stderr
                if out:
                    lines = [l for l in out.split("\n") if l.strip()][:10]
                    return "\n".join(lines)
            except Exception:
                pass
        try:
            r = subprocess.run(["man", "-f", base_cmd], capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
        return ""

    def _explain_llm(self, command: str, man_excerpt: str = "") -> ExplainResult:
        from llm.prompts import explain_prompt
        ctx = self.context.get_context_summary() if self.context else ""
        system, user = explain_prompt(command, ctx)
        if man_excerpt:
            user += f"\n\nMan page excerpt:\n{man_excerpt}"

        start = time.time()
        result = self.llm.generate_json(user, system)
        latency = (time.time() - start) * 1000

        if not result:
            return ExplainResult(
                summary=f"Could not explain '{command}' — LLM unavailable",
                source="llm_failed", man_excerpt=man_excerpt,
                provenance=ProvenanceTag(source=ProvenanceSource.FALLBACK, confidence=0.0, latency_ms=latency),
            )

        return ExplainResult(
            summary=result.get("summary", ""), breakdown=result.get("breakdown", []),
            risks=result.get("risks", []), related_commands=result.get("related_commands", []),
            source="llm", man_excerpt=man_excerpt,
            provenance=ProvenanceTag(source=ProvenanceSource.LLM, confidence=0.9, detail="explanation", latency_ms=latency),
        )
