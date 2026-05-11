# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
# NeuroShell Extensions — Production Module Registry

# ── Core extensions ──
from extensions.plugin_system import PluginSystem
from extensions.workspace_profiles import WorkspaceProfileManager
from extensions.session_recorder import SessionRecorder
from extensions.auto_docs import AutoDocsGenerator
from extensions.clipboard import ClipboardManager

# ── Tier 1: Game Changers ──
from extensions.agent_mode import AutonomousAgent, SmartErrorRecovery
from extensions.smart_intel import explain_command, score_risk, detect_project, RiskAssessment, ProjectInfo
from extensions.platform_features import VoiceCommandEngine, SmartNotifications, NeuroShellAPI, MachineSync

# ── Tier 2: Enterprise ──
from extensions.enterprise import WorkflowEngine, VulnerabilityScanner, AuditTrail, UserRole
from extensions.session_memory import SessionMemory

# ── Tier 3+4: Desktop & Ecosystem ──
from extensions.desktop_features import (
    CommandPalette, SnippetManager, ThemeEngine, NotebookMode,
    DiffPreview, SmartAutocomplete,
)
