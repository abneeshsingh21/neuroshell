# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Help System
Interactive tutorial and contextual help with smart hints.
"""

from dataclasses import dataclass


@dataclass
class HelpEntry:
    """A help topic."""
    topic: str
    title: str
    content: str
    examples: list[str]


class HelpSystem:
    """Contextual help and smart hints."""

    TOPICS = {
        "translate": HelpEntry(
            topic="translate",
            title="Natural Language Translation",
            content="Type in plain English and NeuroShell will convert it to a shell command.\n"
                    "The NLP layer classifies your intent instantly, then the LLM translates complex requests.",
            examples=[
                '"show me big files" → find . -size +100M',
                '"compress this folder" → tar -czf folder.tar.gz folder/',
                '"find all TODO comments" → grep -rn "TODO" .',
            ],
        ),
        "fix": HelpEntry(
            topic="fix",
            title="Error Auto-Fix",
            content="When a command fails, type 'fix' and NeuroShell will analyze the error\n"
                    "and suggest a fix. Previously successful fixes are cached for instant reuse.",
            examples=[
                'Type "fix" after any error',
                'Type "fix last error" for explicit fix request',
            ],
        ),
        "safety": HelpEntry(
            topic="safety",
            title="Safety System",
            content="Three-layer safety checks EVERY command:\n"
                    "1. Pattern matching (instant): blocks rm -rf /, format C:, fork bombs\n"
                    "2. Regex analysis (ms): flags destructive commands for confirmation\n"
                    "3. LLM analysis (only when ambiguous): deep safety check",
            examples=[
                'rm -rf / → ⛔ BLOCKED',
                'rm file.txt → ⚠️ CAUTION: File deletion [Y/n]',
                'ls -la → ✅ SAFE',
            ],
        ),
        "explain": HelpEntry(
            topic="explain",
            title="Command Explainer",
            content="Use 'explain: <command>' to get a detailed breakdown of any command.",
            examples=[
                'explain: tar -xzf archive.tar.gz',
                'explain: chmod 755 script.sh',
            ],
        ),
        "undo": HelpEntry(
            topic="undo",
            title="Undo / Rollback",
            content="Type 'undo' to restore files modified by the last command.\n"
                    "NeuroShell takes snapshots before destructive operations.",
            examples=[
                'Type "undo" after accidentally deleting a file',
            ],
        ),
        "search": HelpEntry(
            topic="search",
            title="Semantic Search",
            content="Search your command history by meaning, not keywords.\n"
                    "Uses AI embeddings to find commands even with different wording.",
            examples=[
                'search: "that docker fix I used last week"',
                'search: "cleaning up disk space"',
            ],
        ),
        "dashboard": HelpEntry(
            topic="dashboard",
            title="Dashboard (F2)",
            content="Press F2 to open the dashboard showing:\n"
                    "• Session stats and uptime\n"
                    "• Feedback accuracy (accept/reject rates)\n"
                    "• Provenance breakdown (LLM vs cached vs pattern)\n"
                    "• Pipeline traces",
            examples=["Press F2"],
        ),
        "policy": HelpEntry(
            topic="policy",
            title="Safety Policy Profiles & Roles",
            content="NeuroShell supports policy profiles and user roles for production governance.\n"
                    "Profiles: dev, staging, production\n"
                    "Roles: admin, developer, operator, viewer\n"
                    "Use policy commands to inspect and update active safety context at runtime.\n"
                    "Safety audit logs can be exported to JSON/CSV and include hash-chain metadata.",
            examples=[
                'policy',
                'policy profile production',
                'policy role operator',
                'policy audit export',
                'policy audit export ./audit.csv',
                'policy audit verify ./audit.csv',
                'help safety',
            ],
        ),
        "plugins": HelpEntry(
            topic="plugins",
            title="Plugin Trust & Capabilities",
            content="Plugins are trust-gated and capability-limited in production mode.\n"
                    "Untrusted plugins are blocked by default unless explicitly trusted.\n"
                    "Capabilities control what plugins may do (execute commands, register hooks).",
            examples=[
                'Set env: NEUROSHELL_ALLOW_UNTRUSTED_PLUGINS=false',
                'Trust plugin by name/hash via PluginSystem API',
                'Review loaded plugin capabilities in dashboard/logs',
            ],
        ),
        "deploy": HelpEntry(
            topic="deploy",
            title="Deployment Promotion & Rollback",
            content="NeuroShell supports staged deployment metadata with release verification.\n"
                    "Use promote for signature-verified releases, rollback for fast recovery,\n"
                    "drift checks to validate runtime config integrity, and canary rollout auto-rollback\n"
                    "based on SLO budget burn. Trusted key allowlist is required for verified promotion.",
            examples=[
                'deploy status',
                'deploy key add ./keys/release-public.pem',
                'deploy key list',
                'deploy promote production 4.1.0 ./deploy/profiles/production.toml ./dist/release-manifest.json ./dist/SHA256SUMS ./keys/release-public.pem',
                'deploy canary production 4.1.0 ./deploy/profiles/production.toml ./dist/release-manifest.json ./dist/SHA256SUMS ./keys/release-public.pem 1.0',
                'deploy rollback',
                'deploy drift ./deploy/profiles/production.toml',
                'deploy audit export ./deploy_audit.json',
                'deploy audit verify ./deploy_audit.json',
            ],
        ),
        "browser": HelpEntry(
            topic="browser",
            title="Browser Access & Automation",
            content="NeuroShell now supports production browser workflows.\n"
                    "Use lightweight fetch/extract for web intelligence and optional\n"
                    "Playwright-powered screenshot automation for deterministic capture.",
            examples=[
                'browser status',
                'browser open https://example.com',
                'browser fetch https://example.com',
                'browser extract https://example.com',
                'browser screenshot https://example.com ./artifacts/home.png',
                'pip install playwright && playwright install chromium',
            ],
        ),
        "github": HelpEntry(
            topic="github",
            title="GitHub API-Style Operations",
            content="NeuroShell can manage PRs and issues via GitHub CLI (gh) with auth checks.\n"
                    "This extends beyond plain git so you can inspect and automate repository collaboration.",
            examples=[
                'github status',
                'github repo set owner/repo',
                'github repo current',
                'github repo --repo owner/repo',
                'github pr list open',
                'github pr view 42 --repo owner/repo',
                'github pr create "Release 4.1" "Production release notes" --base main --head release/4.1 --repo owner/repo',
                'github issue list open --repo owner/repo',
                'github issue create "Bug: crash" "Steps to reproduce..." --repo owner/repo',
                'gh auth login',
            ],
        ),
    }

    def __init__(self, config):
        self.config = config
        self._shown_hints: set = set()

    def get_help(self, topic: str = "") -> str:
        """Get help on a topic, or show all topics."""
        if not topic:
            lines = ["📖 NeuroShell Help Topics:\n"]
            for key, entry in self.TOPICS.items():
                lines.append(f"  help {key:<12} → {entry.title}")
            lines.append("\n  Type 'help <topic>' for details")
            return "\n".join(lines)

        entry = self.TOPICS.get(topic.lower())
        if not entry:
            return f"❓ Unknown topic: '{topic}'. Type 'help' to see all topics."

        lines = [f"\n📖 {entry.title}", "─" * 40, entry.content, "\nExamples:"]
        for ex in entry.examples:
            lines.append(f"  {ex}")
        return "\n".join(lines)

    def get_hint(self, context: str) -> str | None:
        """Get a contextual hint based on current situation."""
        if not self.config.hints_enabled:
            return None

        hints = {
            "first_error": '💡 Tip: Type "fix" to auto-fix that error',
            "first_nl": "💡 Tip: I can translate natural language → shell commands",
            "first_danger": "💡 Tip: I block dangerous commands automatically. Type 'help safety'",
            "first_policy": "💡 Tip: Use 'policy' to view active safety profile and role",
            "long_output": "💡 Tip: Press F2 to see the dashboard",
        }

        hint = hints.get(context)
        if hint and context not in self._shown_hints:
            self._shown_hints.add(context)
            return hint
        return None


class OnboardingTutorial:
    """Interactive first-time tutorial."""

    STEPS = [
        {
            "title": "Welcome to NeuroShell! 🧠",
            "content": "I'm your AI-powered terminal. I understand English AND shell commands.",
            "prompt": "Try typing: show me all files",
        },
        {
            "title": "Safety First 🛡️",
            "content": "I check every command for safety. Dangerous commands get blocked automatically.",
            "prompt": "Try typing: rm -rf /   (don't worry, I'll block it!)",
        },
        {
            "title": "Error Auto-Fix 🔧",
            "content": "When something fails, I can analyze the error and suggest a fix.",
            "prompt": 'Try running a command that fails, then type: fix',
        },
        {
            "title": "Command Explanation 📖",
            "content": "I can break down any command into simple explanations.",
            "prompt": "Try typing: explain: tar -xzf archive.tar.gz",
        },
        {
            "title": "You're Ready! 🚀",
            "content": "Type 'help' anytime to see all features.\n"
                       "Press F2 for the dashboard. Type 'undo' to rollback.\n"
                       "I learn from your patterns — the more you use me, the smarter I get!",
            "prompt": "",
        },
    ]

    def __init__(self):
        self._current_step = 0
        self._completed = False

    @property
    def is_completed(self) -> bool:
        return self._completed

    def get_current_step(self) -> dict | None:
        if self._current_step >= len(self.STEPS):
            self._completed = True
            return None
        return self.STEPS[self._current_step]

    def advance(self):
        self._current_step += 1
        if self._current_step >= len(self.STEPS):
            self._completed = True

    def skip(self):
        self._completed = True
