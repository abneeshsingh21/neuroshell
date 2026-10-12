"""
NeuroShell Standard Edition.
Designed for general software developers, polyglot compiler orchestration,
Git lifecycle workflows, and daily system engineering.
"""

from editions.standard.dev_patterns import DEV_PATTERNS, translate_dev_intent
from operations.code_runner import ExecutionResult, UniversalCodeRunner
from operations.git_ops import GitOps
from operations.github_access import GitHubAccessManager

__all__ = [
    "UniversalCodeRunner",
    "ExecutionResult",
    "GitOps",
    "GitHubAccessManager",
    "DEV_PATTERNS",
    "translate_dev_intent",
]
