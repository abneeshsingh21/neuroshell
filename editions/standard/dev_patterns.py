"""
NeuroShell Standard Edition — Developer Pattern Catalog.
Maps plain-English developer intents to polyglot compiler/runtime invocations
and Git lifecycle operations.
"""

from __future__ import annotations

import re
from typing import Optional


DEV_PATTERNS = [
    # Polyglot Execution
    (r"^(?:run|execute|launch|start)\s+([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)$", "run {0}"),
    (r"^(?:compile|build)\s+([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)$", "compile {0}"),

    # Git Undo / Revert / Reflog
    (r"^(?:undo\s+commit|uncommit|undo\s+last\s+commit|soft\s+undo)$", "git reset --soft HEAD~1"),
    (r"^(?:hard\s+undo|discard\s+last\s+commit|reset\s+hard)$", "git reset --hard HEAD~1"),
    (r"^(?:revert\s+commit|revert)\s+([a-fA-F0-9]+)$", "git revert --no-edit {0}"),
    (r"^(?:show\s+reflog|view\s+reflog|git\s+reflog|reflog\s+history)$", "git reflog -n 15"),
    (r"^(?:git\s+history|show\s+git\s+history|recent\s+commits)$", "git log --oneline -n 10"),

    # GitHub Repository Management
    (r"^(?:delete\s+repo(?:sitory)?|remove\s+repo(?:sitory)?)\s+([\w\.\-]+/[\w\.\-]+)$", "gh repo delete {0} --yes"),
    (r"^(?:view\s+repo|open\s+repo)\s+([\w\.\-]+/[\w\.\-]+)$", "gh repo view {0} --web"),
    (r"^(?:clone\s+repo|clone)\s+([\w\.\-]+/[\w\.\-]+)$", "gh repo clone {0}"),

    # Git Workflows
    (r"^(?:git\s+status|check\s+status|show\s+status)$", "git status"),
    (r"^(?:pull\s+changes|pull\s+latest|git\s+pull)$", "git pull"),
    (r"^(?:push\s+changes|push\s+to\s+remote|git\s+push)$", "git push"),
    (r"^(?:create\s+branch|new\s+branch)\s+([a-zA-Z0-9_\-/]+)$", "git checkout -b {0}"),
    (r"^(?:switch\s+branch|checkout\s+branch)\s+([a-zA-Z0-9_\-/]+)$", "git checkout {0}"),
    (r"^(?:stash\s+changes|save\s+stash|git\s+stash)$", "git stash"),
    (r"^(?:pop\s+stash|apply\s+stash)$", "git stash pop"),
    (r"^(?:clean\s+workspace|git\s+clean)$", "git clean -fd"),

    # Network Administration & Device Discovery
    (r"^(?:find|discover|show|list|get)\s+(?:all\s+)?(?:other\s+)?(?:ip\s+address(?:es)?|ips|devices|hosts)\s+(?:connected\s+to|on|in)\s+(?:my\s+)?(?:network|wifi|lan)$", "arp -a"),
    (r"^(?:scan|discover)\s+(?:my\s+)?local\s+network$", "arp -a"),
    (r"^(?:show|get|what\s+is)\s+(?:my\s+)?(?:ip\s+address|local\s+ip)$", "ipconfig"),
]


def translate_dev_intent(query: str) -> Optional[str]:
    """Translate a plain-English developer intent into a command."""
    q = query.strip()
    for pattern, template in DEV_PATTERNS:
        m = re.match(pattern, q, re.IGNORECASE)
        if m:
            groups = m.groups()
            if groups:
                return template.format(*groups)
            return template
    return None
