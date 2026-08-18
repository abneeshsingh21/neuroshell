# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
# NeuroShell Extensions — Production Module Registry

# ── Core extensions ──
# ── Tier 1: Game Changers ──
from extensions.agent_mode import AutonomousAgent, SmartErrorRecovery
from extensions.auto_docs import AutoDocsGenerator
from extensions.clipboard import ClipboardManager

# ── Tier 3+4: Desktop & Ecosystem ──
from extensions.desktop_features import (
    CommandPalette,
    DiffPreview,
    NotebookMode,
    SmartAutocomplete,
    SnippetManager,
    ThemeEngine,
)

# ── Tier 2: Enterprise ──
from extensions.enterprise import AuditTrail, UserRole, VulnerabilityScanner, WorkflowEngine
from extensions.platform_features import MachineSync, NeuroShellAPI, SmartNotifications, VoiceCommandEngine
from extensions.plugin_system import PluginSystem
from extensions.session_memory import SessionMemory
from extensions.session_recorder import SessionRecorder
from extensions.smart_intel import ProjectInfo, RiskAssessment, detect_project, explain_command, score_risk
from extensions.workspace_profiles import WorkspaceProfileManager
