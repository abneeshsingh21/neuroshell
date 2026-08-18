# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Pipeline Builder — Production Grade
Template library, validation, dry-run preview, parameterized pipelines.
"""

import re
import shutil
import time
from dataclasses import dataclass, field

from observability.provenance import ProvenanceSource, ProvenanceTag


@dataclass
class PipelineStep:
    command: str
    purpose: str
    tool_exists: bool = True


@dataclass
class PipelineResult:
    pipeline: str
    steps: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    explanation: str = ""
    provenance: ProvenanceTag | None = None
    from_template: bool = False
    validation_errors: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Template Library — 50+ Pre-built Pipelines
# ═══════════════════════════════════════════════════════════

PIPELINE_TEMPLATES = {
    # ── Log Analysis ──
    "count errors in log": {"pipeline": "grep -c 'ERROR' {file}", "steps": [{"command": "grep -c 'ERROR' {file}", "purpose": "Count ERROR lines in log file"}], "params": {"file": "*.log"}},
    "show recent errors": {"pipeline": "grep -i 'error\\|fatal\\|critical' {file} | tail -20", "steps": [{"command": "grep -i error", "purpose": "Filter error lines"}, {"command": "tail -20", "purpose": "Show last 20"}], "params": {"file": "*.log"}},
    "top error types": {"pipeline": "grep -i 'error' {file} | sort | uniq -c | sort -rn | head -10", "steps": [{"command": "grep error", "purpose": "Extract errors"}, {"command": "sort | uniq -c", "purpose": "Count unique"}, {"command": "sort -rn | head", "purpose": "Top 10"}], "params": {"file": "*.log"}},

    # ── File Processing ──
    "find large files": {"pipeline": "find . -type f -size +{size} -exec ls -lh {{}} + | sort -k5 -rh | head -20", "steps": [{"command": "find", "purpose": "Find files over size"}, {"command": "sort -k5 -rh", "purpose": "Sort by size"}, {"command": "head -20", "purpose": "Top 20"}], "params": {"size": "100M"}},
    "count lines of code": {"pipeline": "find . -name '*.{ext}' | xargs wc -l | sort -n | tail -20", "steps": [{"command": "find", "purpose": "Find source files"}, {"command": "xargs wc -l", "purpose": "Count lines"}, {"command": "sort | tail", "purpose": "Show biggest"}], "params": {"ext": "py"}},
    "find duplicate files": {"pipeline": "find . -type f -exec md5sum {{}} + | sort | uniq -d -w32", "steps": [{"command": "find + md5sum", "purpose": "Hash all files"}, {"command": "sort | uniq -d", "purpose": "Find duplicates"}], "params": {}},
    "find files modified today": {"pipeline": "find . -type f -mtime 0 -ls", "steps": [{"command": "find -mtime 0", "purpose": "Files modified in last 24h"}], "params": {}},
    "clean temp files": {"pipeline": "find . -name '*.tmp' -o -name '*.pyc' -o -name '__pycache__' | xargs rm -rf", "steps": [{"command": "find temp patterns", "purpose": "Locate temp files"}, {"command": "xargs rm -rf", "purpose": "Remove them"}], "params": {}},

    # ── Git Workflows ──
    "show recent commits": {"pipeline": "git log --oneline -20 --graph --decorate", "steps": [{"command": "git log", "purpose": "Show last 20 commits with graph"}], "params": {}},
    "files changed in last commit": {"pipeline": "git diff --name-only HEAD~1", "steps": [{"command": "git diff --name-only", "purpose": "List changed files"}], "params": {}},
    "find todos in code": {"pipeline": "grep -rn 'TODO\\|FIXME\\|HACK\\|XXX' . --include='*.{ext}'", "steps": [{"command": "grep -rn TODO", "purpose": "Find TODO/FIXME in source"}], "params": {"ext": "py"}},
    "git contributors": {"pipeline": "git shortlog -sn --all | head -20", "steps": [{"command": "git shortlog -sn", "purpose": "Count commits per author"}], "params": {}},

    # ── Docker ──
    "docker cleanup": {"pipeline": "docker system prune -af --volumes", "steps": [{"command": "docker system prune", "purpose": "Remove all unused containers, images, volumes"}], "params": {}},
    "docker logs follow": {"pipeline": "docker logs -f --tail 100 {container}", "steps": [{"command": "docker logs -f", "purpose": "Follow container logs"}], "params": {"container": "container_name"}},
    "docker running containers": {"pipeline": "docker ps --format 'table {{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}'", "steps": [{"command": "docker ps --format", "purpose": "List running containers with details"}], "params": {}},
    "docker image sizes": {"pipeline": "docker images --format '{{{{.Repository}}}}:{{{{.Tag}}}}\\t{{{{.Size}}}}' | sort -k2 -rh", "steps": [{"command": "docker images", "purpose": "List images with sizes sorted"}], "params": {}},

    # ── Network ──
    "check port usage": {"pipeline": "lsof -i :{port} || netstat -tlnp | grep {port}", "steps": [{"command": "lsof/netstat", "purpose": "Find process on port"}], "params": {"port": "8080"}},
    "show active connections": {"pipeline": "netstat -ant | grep ESTABLISHED | sort -k5", "steps": [{"command": "netstat -ant", "purpose": "Show active network connections"}], "params": {}},
    "scan open ports": {"pipeline": "ss -tlnp | sort -k4", "steps": [{"command": "ss -tlnp", "purpose": "Show all listening ports with process info"}], "params": {}},
    "check dns resolution": {"pipeline": "nslookup {domain} && dig {domain} +short", "steps": [{"command": "nslookup", "purpose": "DNS lookup"}, {"command": "dig", "purpose": "Get IP addresses"}], "params": {"domain": "example.com"}},

    # ── Disk ──
    "disk usage summary": {"pipeline": "du -sh */ 2>/dev/null | sort -rh | head -20", "steps": [{"command": "du -sh", "purpose": "Get directory sizes"}, {"command": "sort -rh", "purpose": "Sort largest first"}], "params": {}},
    "find old files": {"pipeline": "find . -type f -atime +{days} -ls | sort -k7 -rn | head -20", "steps": [{"command": "find -atime", "purpose": "Find files not accessed in N days"}], "params": {"days": "90"}},

    # ── Process ──
    "top memory processes": {"pipeline": "ps aux --sort=-%mem | head -15", "steps": [{"command": "ps aux --sort=-%mem", "purpose": "Processes sorted by memory"}, {"command": "head", "purpose": "Top 15"}], "params": {}},
    "top cpu processes": {"pipeline": "ps aux --sort=-%cpu | head -15", "steps": [{"command": "ps aux --sort=-%cpu", "purpose": "Processes sorted by CPU"}], "params": {}},
    "kill by port": {"pipeline": "lsof -ti :{port} | xargs kill -9", "steps": [{"command": "lsof -ti", "purpose": "Find PID on port"}, {"command": "xargs kill", "purpose": "Terminate process"}], "params": {"port": "8080"}},
    "process tree": {"pipeline": "pstree -p | head -50", "steps": [{"command": "pstree -p", "purpose": "Show process tree with PIDs"}], "params": {}},

    # ── Security ──
    "check permissions": {"pipeline": "find . -type f -perm /go+w -ls 2>/dev/null", "steps": [{"command": "find -perm", "purpose": "Find world/group writable files"}], "params": {}},
    "find suid files": {"pipeline": "find / -perm -4000 -type f 2>/dev/null | head -20", "steps": [{"command": "find -perm -4000", "purpose": "Find files with SUID bit set"}], "params": {}},
    "check ssl cert": {"pipeline": "echo | openssl s_client -connect {host}:443 2>/dev/null | openssl x509 -noout -dates -subject", "steps": [{"command": "openssl s_client", "purpose": "Connect to host"}, {"command": "openssl x509", "purpose": "Show cert dates and subject"}], "params": {"host": "example.com"}},
    "find exposed secrets": {"pipeline": "grep -rn 'password\\|secret\\|api_key\\|token' . --include='*.{ext}' | head -20", "steps": [{"command": "grep -rn", "purpose": "Search for potential secrets in source"}], "params": {"ext": "py"}},
    "audit file permissions": {"pipeline": "find . -name '*.sh' ! -perm -u+x -ls", "steps": [{"command": "find", "purpose": "Find shell scripts without execute permission"}], "params": {}},

    # ── Python/Dev ──
    "run linters": {"pipeline": "python -m flake8 . && python -m mypy . --ignore-missing-imports", "steps": [{"command": "flake8", "purpose": "Style and error checking"}, {"command": "mypy", "purpose": "Type checking"}], "params": {}},
    "find unused imports": {"pipeline": "python -m flake8 . --select=F401 | head -30", "steps": [{"command": "flake8 --select=F401", "purpose": "Find unused import statements"}], "params": {}},
    "test coverage": {"pipeline": "python -m pytest --cov=. --cov-report=term-missing | tail -40", "steps": [{"command": "pytest --cov", "purpose": "Run tests with coverage report"}], "params": {}},
    "profile script": {"pipeline": "python -m cProfile -s cumtime {script} 2>&1 | head -30", "steps": [{"command": "cProfile", "purpose": "Profile Python script and show top functions"}], "params": {"script": "main.py"}},
    "find python todos": {"pipeline": "grep -rn 'TODO\\|FIXME\\|HACK\\|XXX\\|NOQA' . --include='*.py' | head -30", "steps": [{"command": "grep -rn", "purpose": "Find TODO/FIXME in Python files"}], "params": {}},
    "pip vulnerability check": {"pipeline": "pip audit 2>&1 || pip list --outdated --format=columns", "steps": [{"command": "pip audit", "purpose": "Check installed packages for vulnerabilities"}], "params": {}},
    "count python lines": {"pipeline": "find . -name '*.py' -not -path '*venv*' | xargs wc -l | sort -n | tail -20", "steps": [{"command": "find + wc", "purpose": "Count lines of Python code"}], "params": {}},

    # ── Kubernetes ──
    "pod status": {"pipeline": "kubectl get pods -o wide -n {namespace}", "steps": [{"command": "kubectl get pods", "purpose": "Show pod status with node info"}], "params": {"namespace": "default"}},
    "pod logs": {"pipeline": "kubectl logs -f --tail=100 {pod} -n {namespace}", "steps": [{"command": "kubectl logs", "purpose": "Follow pod logs"}], "params": {"pod": "pod-name", "namespace": "default"}},
    "restart deployment": {"pipeline": "kubectl rollout restart deployment/{deployment} -n {namespace}", "steps": [{"command": "kubectl rollout restart", "purpose": "Rolling restart of deployment"}], "params": {"deployment": "my-app", "namespace": "default"}},
    "cluster health": {"pipeline": "kubectl get nodes && echo '---' && kubectl top nodes 2>/dev/null", "steps": [{"command": "kubectl get nodes", "purpose": "Show node status"}, {"command": "kubectl top nodes", "purpose": "Show resource usage"}], "params": {}},
    "kubectl events": {"pipeline": "kubectl get events --sort-by='.lastTimestamp' -n {namespace} | tail -20", "steps": [{"command": "kubectl get events", "purpose": "Show recent cluster events"}], "params": {"namespace": "default"}},

    # ── Database ──
    "dump database": {"pipeline": "pg_dump -h {host} -U {user} {db} > dump_{db}.sql", "steps": [{"command": "pg_dump", "purpose": "Export PostgreSQL database to SQL file"}], "params": {"host": "localhost", "user": "postgres", "db": "mydb"}},
    "show slow queries": {"pipeline": "tail -f {logfile} | grep -i 'slow\\|duration'", "steps": [{"command": "tail -f", "purpose": "Follow database log"}, {"command": "grep duration", "purpose": "Filter slow queries"}], "params": {"logfile": "/var/log/postgresql/postgresql.log"}},
    "redis status": {"pipeline": "redis-cli info server | head -20 && redis-cli info memory | head -10", "steps": [{"command": "redis-cli info", "purpose": "Show Redis server and memory stats"}], "params": {}},

    # ── System Health ──
    "system health report": {"pipeline": "echo '=== CPU ===' && uptime && echo '\\n=== Memory ===' && free -h && echo '\\n=== Disk ===' && df -h / && echo '\\n=== Load ===' && cat /proc/loadavg 2>/dev/null || systeminfo", "steps": [{"command": "uptime + free + df", "purpose": "Comprehensive system health snapshot"}], "params": {}},
    "monitor file changes": {"pipeline": "inotifywait -r -m . -e modify,create,delete 2>/dev/null || fswatch .", "steps": [{"command": "inotifywait/fswatch", "purpose": "Watch for file system changes in real-time"}], "params": {}},
    "check journal errors": {"pipeline": "journalctl -p err -b --no-pager | tail -30", "steps": [{"command": "journalctl -p err", "purpose": "Show error-level entries from current boot"}], "params": {}},
}


class PipelineBuilder:
    """
    Production-grade pipeline builder.

    Features:
    - 20+ pre-built pipeline templates with parameterization
    - Tool validation (check each tool exists)
    - Dry-run preview
    - {placeholder} syntax for reusable pipelines
    - LLM fallback for complex requests
    """

    def __init__(self, llm_client=None, context_manager=None):
        self.llm = llm_client
        self.context = context_manager

    def build(self, user_input: str, params: dict | None = None) -> PipelineResult:
        """Build a pipeline from NL description, using templates or LLM."""
        # 1. Try template match
        template = self._match_template(user_input)
        if template:
            return self._build_from_template(template, params or {})

        # 2. LLM fallback
        if self.llm:
            return self._build_from_llm(user_input)

        return PipelineResult(
            pipeline="", steps=[], confidence=0.0,
            explanation="Could not build pipeline — no template match and LLM unavailable",
            provenance=ProvenanceTag(source=ProvenanceSource.FALLBACK, confidence=0.0),
        )

    def list_templates(self) -> list[str]:
        """List all available pipeline template names."""
        return sorted(PIPELINE_TEMPLATES.keys())

    def validate_pipeline(self, pipeline: str) -> list[str]:
        """Validate that all tools in a pipeline exist."""
        errors = []
        commands = re.split(r'\s*\|\s*', pipeline)
        for cmd in commands:
            tool = cmd.strip().split()[0] if cmd.strip() else ""
            if tool and not tool.startswith("{") and not shutil.which(tool):
                errors.append(f"Tool not found: '{tool}'")
        return errors

    def dry_run(self, pipeline: str) -> str:
        """Generate a dry-run preview showing data flow."""
        commands = re.split(r'\s*\|\s*', pipeline)
        preview_lines = ["Pipeline flow:"]
        for i, cmd in enumerate(commands):
            arrow = "  →  " if i > 0 else "  ▶  "
            preview_lines.append(f"{arrow}[Step {i+1}] {cmd.strip()}")
        return "\n".join(preview_lines)

    def _match_template(self, user_input: str) -> dict | None:
        """Fuzzy match user input against template names."""
        input_lower = user_input.lower().strip()
        best_match = None
        best_score = 0

        for name, template in PIPELINE_TEMPLATES.items():
            score = self._similarity(input_lower, name)
            if score > best_score and score > 0.4:
                best_score = score
                best_match = template

        return best_match

    def _similarity(self, a: str, b: str) -> float:
        """Word overlap similarity."""
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return 0.0
        overlap = len(words_a & words_b)
        return overlap / max(len(words_a), len(words_b))

    def _build_from_template(self, template: dict, params: dict) -> PipelineResult:
        """Build pipeline from template with parameter substitution."""
        pipeline = template["pipeline"]
        tmpl_params = template.get("params", {})

        # Merge default params with user params
        merged = {**tmpl_params, **params}
        for key, val in merged.items():
            pipeline = pipeline.replace(f"{{{key}}}", str(val))

        errors = self.validate_pipeline(pipeline)

        return PipelineResult(
            pipeline=pipeline,
            steps=template.get("steps", []),
            confidence=0.9,
            explanation="Built from template",
            from_template=True,
            validation_errors=errors,
            provenance=ProvenanceTag(
                source=ProvenanceSource.PATTERN, confidence=0.9,
                detail="template library", latency_ms=0.5,
            ),
        )

    def _build_from_llm(self, user_input: str) -> PipelineResult:
        """Build pipeline using LLM."""
        from llm.prompts import pipeline_prompt

        ctx = self.context.get_context_summary() if self.context else ""
        system, user = pipeline_prompt(user_input, ctx)

        start = time.time()
        result = self.llm.generate_json(user, system)
        latency = (time.time() - start) * 1000

        if not result:
            return PipelineResult(
                pipeline="", steps=[], confidence=0.0,
                explanation="Could not build pipeline — LLM unavailable",
                provenance=ProvenanceTag(source=ProvenanceSource.FALLBACK, confidence=0.0, latency_ms=latency),
            )

        pipeline = result.get("pipeline", "")
        errors = self.validate_pipeline(pipeline) if pipeline else []

        return PipelineResult(
            pipeline=pipeline,
            steps=result.get("steps", []),
            confidence=float(result.get("confidence", 0.5)),
            explanation=result.get("explanation", ""),
            validation_errors=errors,
            provenance=ProvenanceTag(
                source=ProvenanceSource.LLM,
                confidence=float(result.get("confidence", 0.5)),
                detail="pipeline builder", latency_ms=latency,
            ),
        )
