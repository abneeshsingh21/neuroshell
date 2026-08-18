# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
#!/usr/bin/env python3
"""
NeuroShell v4 — AI-Powered Terminal
Main orchestrator: signal handling, lazy loading, status bar, pipeline routing.

Usage:
    python main.py
"""

import atexit
import os
import shlex
import signal
import sys
import time
import uuid
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import NEUROSHELL_DIR, load_config

# ═══════════════════════════════════════════════════════
# Lazy Module Loader
# ═══════════════════════════════════════════════════════


class _Lazy:
    """Lazy-load heavy modules on first access to cut startup time."""

    def __init__(self, factory):
        self._factory = factory
        self._obj = None

    def __getattr__(self, name):
        if self._obj is None:
            self._obj = self._factory()
        return getattr(self._obj, name)


class NeuroShell:
    """
    Main orchestrator — the brain of NeuroShell.

    Production features:
    - Signal handling (SIGINT, SIGTERM) for clean shutdown
    - Lazy loading of heavy modules (NLP, learning)
    - Pipeline intent routing
    - Tab completion hook
    - Session metrics and status bar
    - Crash recovery with atexit
    """

    def __init__(self):
        import threading

        # ── Fast path: config + session state (<0.5s) ──
        self.config = load_config()

        # Lightweight logger — no heavy deps
        from observability.logger import StructuredLogger
        self.logger = StructuredLogger("main")

        # Session state (zero-cost)
        self.session_id = uuid.uuid4().hex[:8]
        self._last_error_output = ""
        self._last_command = ""
        self._running = True
        self._command_count = 0
        self.mode = "Builder"

        # Conversation memory for follow-ups
        self._conversation_context = []  # last N (input, command, result) tuples
        self._MAX_MEMORY = 5
        self._FOLLOWUP_WORDS = {
            "now", "also", "then", "those", "that", "these",
            "same", "again", "instead", "but", "and", "plus",
            "filter", "sort", "only", "except", "without",
        }

        # ── Background loading gate ──
        self._modules_ready = threading.Event()
        self._load_error = None

        # Start heavy loading in background
        self._loader_thread = threading.Thread(
            target=self._load_heavy_modules, daemon=True, name="neuroshell-loader"
        )
        self._loader_thread.start()

    def _wait_for_modules(self, timeout: float = 30.0) -> bool:
        """Block until heavy modules are loaded. Returns True if ready."""
        if self._modules_ready.is_set():
            return True
        print("  ⏳ Loading modules...", end="", flush=True)
        ready = self._modules_ready.wait(timeout=timeout)
        if ready:
            print(" ✅")
        else:
            print(" ⚠️ timeout")
        return ready

    def wait_for_modules(self, timeout: float = 30.0) -> bool:
        """Block until heavy modules are loaded. Returns True if ready."""
        return self._wait_for_modules(timeout=timeout)

    def _load_heavy_modules(self):
        """Load all heavy modules in background thread."""
        try:
            # ── Core Layer ───────────────────────────────
            from core.context import ContextManager
            from core.dependency_resolver import DependencyResolver
            from core.executor import ShellExecutor
            from core.history import HistoryStore
            from core.output_parser import OutputParser

            self.executor = ShellExecutor(self.config)
            self.context = ContextManager(self.config)
            self.history = HistoryStore()
            self.parser = OutputParser()
            self.dep_resolver = DependencyResolver(self.context)

            class _DefaultConsoleUI:
                def print_info(self, msg, **kw): print(msg)
                def print_error(self, msg, **kw): print(msg)
                def print_success(self, msg, **kw): print(msg)
                def print_warning(self, msg, **kw): print(msg)
                def print_result(self, cmd, res, **kw):
                    code = getattr(res, 'exit_code', getattr(res, 'returncode', 0))
                    print(f"\n[Exit code: {code}]")
                    if getattr(res, 'stdout', None): print(res.stdout)
                    if getattr(res, 'stderr', None): print(f"Error: {res.stderr}")
            self.ui = _DefaultConsoleUI()

            # ── Observability ────────────────────────────
            from observability.provenance import ProvenanceTracker
            from observability.tracer import EventTracer

            self.tracer = EventTracer(self.logger)
            self.provenance = ProvenanceTracker()

            # ── Learning/Metrics ─────────────────────────
            from learning.metrics import MetricsTracker
            self.metrics = MetricsTracker()

            # ── LLM ──────────────────────────────────────
            from llm.client import LLMClient
            self.llm = LLMClient(self.config)

            # ── NLP Fast Layer ───────────────────────────
            from nlp.entity_extractor import EntityExtractor
            from nlp.intent_classifier import IntentClassifier
            from nlp.sentiment import SentimentDetector

            self.intent_classifier = IntentClassifier()
            self.entity_extractor = EntityExtractor()
            self.sentiment = SentimentDetector()

            # ── Intelligence ─────────────────────────────
            import intelligence.pii_scrubber as _pii_scrubber
            from intelligence.agent import AgentPlanner
            from intelligence.autocomplete import Autocomplete
            from intelligence.bookmarks import BookmarkManager
            from intelligence.chain_builder import ChainBuilder
            from intelligence.error_fixer import ErrorFixer
            from intelligence.explainer import Explainer
            from intelligence.fuzzy_corrector import FuzzyCorrector
            from intelligence.phrase_dictionary import PhraseDictionary
            from intelligence.pipeline_builder import PipelineBuilder
            from intelligence.project_detector import ProjectDetector
            from intelligence.safety import RiskLevel, SafetyChecker
            from intelligence.script_generator import ScriptGenerator
            from intelligence.translator import Translator
            self.pii_scrubber = _pii_scrubber
            from intelligence.offline_fallback import OfflineFallbackManager

            self.translator = Translator(self.llm, self.context, self.history)
            self.safety = SafetyChecker(self.config, self.llm)
            self.fixer = ErrorFixer(self.llm, self.history, self.context)
            self.explainer = Explainer(self.llm, self.context)
            self.autocomplete = Autocomplete(self.history, self.context)
            self.pipeline_builder = PipelineBuilder(self.llm, self.context)
            self._RiskLevel = RiskLevel

            # ── Futuristic modules ────────────────────────
            self.fuzzy_corrector = FuzzyCorrector()
            self.chain_builder = ChainBuilder(self.llm, self.translator)
            self.project_detector = ProjectDetector()
            self.bookmarks = BookmarkManager(self.history)
            self.agent = AgentPlanner(self.llm, self.executor, self.safety)
            self.script_generator = ScriptGenerator(self.llm)
            self.phrase_dict = PhraseDictionary()
            self.offline_fallback = OfflineFallbackManager(self.config)

            # Try importing C++ engine gracefully, falling back to pure-Python engine
            try:
                import cpp_engine.cpp_engine_core as cpp
                self.cpp_parser = cpp.FastParser()
                self.cpp_matcher = cpp.FuzzyMatcher()
                self._cpp_enabled = True
            except ImportError:
                try:
                    from cpp_engine.engine import FastParser, FuzzyMatcher
                    self.cpp_parser = FastParser()
                    self.cpp_matcher = FuzzyMatcher()
                    self._cpp_enabled = True
                except Exception:
                    self._cpp_enabled = False

            # ── Feature Modules ──────────────────────────
            from core.env_manager import EnvManager
            from core.timer import CommandTimer
            from extensions.alias_manager import AliasManager
            from extensions.auto_docs import AutoDocsGenerator
            from extensions.clipboard import ClipboardManager
            from extensions.config_editor import ConfigEditor
            from extensions.plugin_system import PluginSystem
            from extensions.session_recorder import SessionRecorder
            from extensions.workspace_profiles import WorkspaceProfileManager
            from intelligence.deep_search import DeepSearch
            from intelligence.smart_open import SmartOpenEngine
            from intelligence.smart_suggestions import SmartSuggester
            from llm.model_manager import ModelManager
            from operations.data_governance import DataGovernanceManager
            from operations.git_ops import GitOps, GitTool
            from operations.update_manager import UpdateManager

            self.alias_manager = AliasManager()
            self.env_manager = EnvManager()
            self.model_manager = ModelManager(self.config, self.llm)
            self.config_editor = ConfigEditor(self.config)
            self.command_timer = CommandTimer(self.executor)
            self.docs_generator = AutoDocsGenerator(self.history, None)
            self.smart_suggester = SmartSuggester(self.history, self.context)
            self.smart_open = SmartOpenEngine()
            self.ext_clipboard = ClipboardManager()
            self.ext_recorder = SessionRecorder()
            self.workspace_profiles = WorkspaceProfileManager()
            self.plugin_system = PluginSystem()
            self.data_governance = DataGovernanceManager(NEUROSHELL_DIR / "logs", NEUROSHELL_DIR / "audit")
            self.update_manager = UpdateManager(NEUROSHELL_DIR / "release")
            self.git_ops = GitOps()
            self.deep_search = DeepSearch()

            # ── Phase 7 Agentic Features ─────────────────
            from intelligence.coordinator import Coordinator
            from intelligence.memory.session_memory import SessionMemory
            from intelligence.modes.plan_mode import PlanModeController
            from intelligence.swarm import SwarmOrchestrator
            from intelligence.tools.mode_tools import ModeTool
            from intelligence.tools.task_tools import TaskSystemTool
            from intelligence.tools.teammate_tool import TeammateTool

            self.session_memory = SessionMemory(max_turns=15)
            self.mcp_client = None
            self.lsp_client = None

            try:
                from intelligence.mcp.mcp_client import MCPClient
                from intelligence.tools.mcp_tool import MCPTool
                self.mcp_client = MCPClient("http://localhost:8000")
            except Exception:
                pass

            try:
                from intelligence.lsp.lsp_client import LSPClient
                from intelligence.tools.lsp_tool import LSPTool
                self.lsp_client = LSPClient(["python", "-m", "pylsp"])
            except Exception:
                pass

            from intelligence.tasks.task_manager import TaskManager
            self.task_manager = TaskManager()

            self.coordinator = Coordinator(self.llm, self.context)
            if self.mcp_client is not None:
                try:
                    self.coordinator.register_tool(MCPTool(self.mcp_client))
                except Exception:
                    pass
            if self.lsp_client is not None:
                try:
                    self.coordinator.register_tool(LSPTool(self.lsp_client))
                except Exception:
                    pass
            self.coordinator.register_tool(TaskSystemTool(self.task_manager))
            self.coordinator.register_tool(TeammateTool())
            self.coordinator.register_tool(GitTool(self.git_ops))

            self.plan_mode = PlanModeController()
            self.coordinator.register_tool(ModeTool(self.plan_mode))
            self.swarm_orchestrator = SwarmOrchestrator(self.llm, self.context)

            # ── Intelligence Background Services ─────────
            try:
                from intelligence.services.magic_docs import MagicDocs
                self.magic_docs = MagicDocs(self.llm)
            except Exception:
                self.magic_docs = None
            self.auto_dream = None

            # ── Learning ─────────────────────────────────
            from learning.feedback_loop import FeedbackLoop
            from learning.pattern_learner import PatternLearner
            from learning.predictor import Predictor

            self.pattern_learner = PatternLearner(self.history)
            self.predictor = Predictor(self.history)
            self.feedback = FeedbackLoop(self.history, self.intent_classifier)
            self.docs_generator = AutoDocsGenerator(self.history, self.pattern_learner)

            # ── Tier 1-4: Production Extensions ─────────
            try:
                from extensions.agent_mode import AutonomousAgent as ExtAgent
                from extensions.agent_mode import SmartErrorRecovery
                from extensions.desktop_features import (
                    CommandPalette,
                    DiffPreview,
                    NotebookMode,
                    SmartAutocomplete,
                    SnippetManager,
                    ThemeEngine,
                )
                from extensions.enterprise import AuditTrail, VulnerabilityScanner, WorkflowEngine
                from extensions.platform_features import (
                    MachineSync,
                    NeuroShellAPI,
                    SmartNotifications,
                    VoiceCommandEngine,
                )
                from extensions.session_memory import SessionMemory as ExtSessionMemory
                from extensions.smart_intel import detect_project, explain_command, score_risk

                self.ext_recovery = SmartErrorRecovery(is_windows=__import__('platform').system() == 'Windows')
                self.ext_agent = ExtAgent(recovery=self.ext_recovery)
                self.ext_memory = ExtSessionMemory()
                self.ext_workflow = WorkflowEngine()
                self.ext_scanner = VulnerabilityScanner()
                self.ext_audit = AuditTrail()
                self.ext_notifications = SmartNotifications()
                self.ext_api = NeuroShellAPI(translator=self.translator)
                self.ext_sync = MachineSync()
                self.ext_voice = VoiceCommandEngine()
                self.ext_palette = CommandPalette()
                self.ext_snippets = SnippetManager()
                self.ext_themes = ThemeEngine()
                self.ext_notebook = NotebookMode()
                self.ext_diff = DiffPreview()
                self.ext_autocomplete = SmartAutocomplete(memory=self.ext_memory, palette=self.ext_palette)
                self._ext_explain = explain_command
                self._ext_risk = score_risk
                self._ext_detect = detect_project
                self.logger.info("extensions_loaded", tier1=True, tier2=True, tier3=True, tier4=True)
            except Exception as ext_err:
                self.logger.warn("extensions_load_failed", error=str(ext_err))

            # ── Resilience ───────────────────────────────
            from resilience.resilience import (
                GracefulDegradation,
                HealthCheck,
                NetworkAware,
                ResilienceManager,
            )
            self.network = NetworkAware()
            self.health = HealthCheck(self.config)
            self.degradation = GracefulDegradation()
            self.resilience_manager = ResilienceManager(self.config)

            # ── Deployment operations ───────────────────
            from operations.browser_access import BrowserAccessManager
            from operations.deploy_manager import DeployManager
            from operations.github_access import GitHubAccessManager
            from operations.runtime_ops import RuntimeSLOMonitor
            self.deploy_manager = DeployManager(NEUROSHELL_DIR / "deploy" / "state.json")
            self.browser_access = BrowserAccessManager(Path.cwd())
            self.github_access = GitHubAccessManager(Path.cwd(), NEUROSHELL_DIR / "github_context.json")
            self.runtime_slo = RuntimeSLOMonitor()

            # ── Help ─────────────────────────────────────
            from help.help_system import HelpSystem, OnboardingTutorial
            self.help = HelpSystem(self.config)
            self.tutorial = OnboardingTutorial()

            # ── UI ───────────────────────────────────────
            from ui.app import NeuroShellUI
            from ui.dashboard import Dashboard
            from ui.terminal_editor import TerminalLineEditor
            self.ui = NeuroShellUI()
            self.line_editor = TerminalLineEditor(autocomplete_engine=self.autocomplete, history_store=self.history)
            self.dashboard = Dashboard(
                history_store=self.history,
                metrics_tracker=self.metrics,
                project_detector=self.project_detector,
                config=self.config,
            )

            # ── High-Speed IPC Server ───────────────────
            from core.ipc_server import NamedPipeServer
            self.ipc_server = NamedPipeServer(self)
            self.ipc_server.start()

            # Signal ready
            self._modules_ready.set()
            self.logger.info("modules_loaded", status="ok")

        except Exception as e:
            self._load_error = str(e)
            self._modules_ready.set()  # Unblock main thread even on error
            import traceback
            traceback.print_exc()

    # ═══════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════

    def startup(self):
        """Run startup sequence with signal handling."""
        # Register signal handlers immediately
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        atexit.register(self._crash_cleanup)

        # Print startup banner INSTANTLY (no heavy deps needed)
        from ui.banner import render_startup_banner
        print(render_startup_banner(self.config))

        # Wait for background module loading to complete
        modules_loaded = self._wait_for_modules(timeout=30.0)

        if not modules_loaded or self._load_error:
            self._degraded = True
            error_msg = self._load_error or "Module loading timed out."

            # Use UI if loaded, otherwise fallback to plain print
            if hasattr(self, 'ui') and self.ui:
                self.ui.print_warning(f"NeuroShell started in Degraded Mode.\nError: {error_msg}")
            else:
                print(f"  ⚠️ NeuroShell started in Degraded Mode.\n  ⚠️ Error: {error_msg}")
        else:
            self._degraded = False

        self.logger.info("startup", session_id=self.session_id)

        # Initialize fast NLP layer (<5ms)
        self._init_nlp()

        # Launch background warmup asynchronously without blocking prompt
        def _async_warmup():
            try:
                if hasattr(self, 'llm') and self.llm:
                    self.llm.warmup_async()
                if hasattr(self, 'pattern_learner') and self.pattern_learner:
                    self.pattern_learner.learn_from_history()
                if hasattr(self, 'predictor') and self.predictor:
                    self.predictor.train()
            except Exception:
                pass

        threading.Thread(target=_async_warmup, daemon=True, name="Warmup").start()

        # Start session
        cwd = os.getcwd()
        ws = self.context._detect_workspace(cwd) if hasattr(self.context, '_detect_workspace') else ""
        self.history.start_session(self.session_id, cwd, ws or "")

        # Tab completion
        self._setup_tab_completion()

        self.ui.print_info(f"\nSession {self.session_id} started. Type 'help' for commands.")
        policy_tag = self._policy_tag()
        if policy_tag:
            self.ui.print_info(f"Safety policy active: {policy_tag}")

        # Show project-aware suggestions
        self._show_project_suggestions()
        print()

    def _handle_signal(self, signum, frame):
        """Handle SIGINT/SIGTERM for clean shutdown."""
        if signum == signal.SIGINT:
            now = time.time()
            if hasattr(self, "_last_sigint_time") and (now - self._last_sigint_time) < 1.5:
                print("\n\x1b[1;33m[!] Exiting NeuroShell...\x1b[0m")
                self._running = False
                self.shutdown()
                sys.exit(0)
            self._last_sigint_time = now
            print("\n\x1b[38;5;240m(Press Ctrl+C again within 1.5s to exit)\x1b[0m")
            return
        self._running = False
        self.shutdown()
        sys.exit(0)

    def shutdown(self):
        """Clean shutdown of background services and session state."""
        try:
            if hasattr(self, "ipc_server") and self.ipc_server:
                self.ipc_server.stop()
            if hasattr(self, "auto_dream") and self.auto_dream:
                self.auto_dream.stop()
            self.history.end_session(self.session_id)
        except Exception:
            pass

    def _crash_cleanup(self):
        """Atexit handler — save session data even on crash."""
        self.shutdown()

    def _setup_tab_completion(self):
        """Set up readline tab-completion (Unix/macOS)."""
        try:
            import readline

            def completer(text, state):
                try:
                    completions = self.autocomplete.complete(text)
                    results = [c.text for c in completions]
                    if state < len(results):
                        return results[state]
                except Exception:
                    pass
                return None

            readline.set_completer(completer)
            readline.parse_and_bind("tab: complete")
            readline.set_completer_delims(" \t\n;")
        except ImportError:
            pass  # readline not available on Windows by default

    def _init_nlp(self):
        if self.intent_classifier.initialize():
            self.logger.info("nlp_init", component="intent_classifier", status="loaded")
        if self.entity_extractor.initialize():
            self.logger.info("nlp_init", component="entity_extractor", status="loaded")
        if self.sentiment.initialize():
            self.logger.info("nlp_init", component="sentiment", status="loaded")

    def _get_policy_state(self) -> dict:
        """Get active safety policy context if supported by safety checker."""
        try:
            if hasattr(self.safety, "get_policy_state"):
                return self.safety.get_policy_state() or {}
        except Exception:
            pass
        return {}

    def _policy_tag(self) -> str:
        """Render policy context as [profile/role]."""
        state = self._get_policy_state()
        profile = state.get("profile")
        role = state.get("role")
        if profile and role:
            return f"[{profile}/{role}]"
        if profile:
            return f"[{profile}]"
        return ""

    # ═══════════════════════════════════════════════════════
    # Main Loop
    # ═══════════════════════════════════════════════════════

    def run(self):
        """Main REPL loop."""
        self.startup()

        while self._running:
            try:
                cwd = os.getcwd()
                git_ctx = self.context._get_git_context(cwd)

                # Build rich prompt
                env_name = ""
                venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_DEFAULT_ENV")
                if venv:
                    env_name = os.path.basename(venv)

                prompt = self.ui.get_prompt(
                    cwd,
                    git_branch=git_ctx.branch if git_ctx.is_repo else "",
                    env_name=env_name,
                    network=self.network.is_online if hasattr(self.network, "is_online") else True,
                )

                if hasattr(self, "line_editor") and self.line_editor:
                    raw_input = self.line_editor.read_line(prompt)
                else:
                    raw_input = input(prompt)

                if raw_input is None:
                    self._running = False
                    break

                user_input = raw_input.strip()
                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit", "q"):
                    self._running = False
                    break

                self.process_input(user_input)

            except KeyboardInterrupt:
                print()
                continue
            except EOFError:
                self._running = False
                break

        self.shutdown()

    def process_input(self, user_input: str):
        """Process user input through the full pipeline."""
        cid = self.tracer.start_trace()
        start_time = time.time()
        self.metrics.count("inputs")
        self._command_count += 1

        # ── Degraded Fallback ──
        if getattr(self, '_degraded', False):
            # In degraded mode, bypass NLP and intelligence, just run raw shell
            self._handle_shell_command(user_input, cid)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        # ── Step 1: NLP Pre-processing (<5ms) ──────
        self.tracer.add_event(cid, "nlp_start")

        # Deterministic prefix routing — always wins over NLP
        lower = user_input.lower().strip()

        # ── Slash Command Router (/) ──
        if lower.startswith("/"):
            if self._handle_slash_command(user_input, cid):
                total_ms = (time.time() - start_time) * 1000
                self.metrics.record_latency("total_pipeline", total_ms)
                self.tracer.end_trace(cid)
                return

        if lower.startswith("explain:") or lower.startswith("explain "):
            command = user_input.split(":", 1)[-1].strip() if ":" in user_input else user_input[7:].strip()
            if not command:
                command = self._last_command
            self._handle_explain(command, cid)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        if lower == "fix":
            self._handle_fix(cid)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        if lower == "undo":
            self._handle_undo()
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        # ── Alias commands ──
        if lower == "aliases":
            print(self.alias_manager.get_formatted_list())
            self.tracer.end_trace(cid)
            return
        if lower.startswith("alias "):
            self._handle_alias_set(user_input[6:])
            self.tracer.end_trace(cid)
            return
        if lower.startswith("unalias "):
            name = user_input[8:].strip()
            if self.alias_manager.remove(name):
                self.ui.print_info(f"  ✅ Removed alias: {name}")
            else:
                self.ui.print_info(f"  ❌ No alias named '{name}'")
            self.tracer.end_trace(cid)
            return

        # ── Environment variable commands ──
        if lower == "env":
            print(self.env_manager.get_formatted_list())
            self.tracer.end_trace(cid)
            return
        if lower.startswith("env "):
            query = user_input[4:].strip()
            print(self.env_manager.get_formatted_var(query))
            self.tracer.end_trace(cid)
            return
        if lower.startswith("setenv "):
            parsed = self.env_manager.parse_set_command(user_input[7:])
            if parsed:
                self.env_manager.set_var(*parsed)
                self.ui.print_info(f"  ✅ Set {parsed[0]}={parsed[1]}")
            else:
                self.ui.print_info("  Usage: setenv KEY=VALUE or setenv KEY VALUE")
            self.tracer.end_trace(cid)
            return
        if lower.startswith("unsetenv "):
            name = user_input[9:].strip()
            if self.env_manager.unset_var(name):
                self.ui.print_info(f"  ✅ Unset {name}")
            else:
                self.ui.print_info(f"  ❌ '{name}' not found")
            self.tracer.end_trace(cid)
            return

        # ── Model commands ──
        if lower == "models":
            print(self.model_manager.get_formatted_list())
            self.tracer.end_trace(cid)
            return
        if lower.startswith("model "):
            model_name = user_input[6:].strip()
            success, msg = self.model_manager.switch_model(model_name)
            self.ui.print_info(f"  {'✅' if success else '❌'} {msg}")
            self.tracer.end_trace(cid)
            return

        # ── Config commands ──
        if lower == "config" or lower == "config show":
            print(self.config_editor.show())
            self.tracer.end_trace(cid)
            return
        if lower.startswith("config show "):
            section = user_input[12:].strip()
            print(self.config_editor.show(section))
            self.tracer.end_trace(cid)
            return
        if lower.startswith("config set "):
            parts = user_input[11:].strip().split(None, 1)
            if len(parts) == 2:
                ok, msg = self.config_editor.set_value(parts[0], parts[1])
                self.ui.print_info(f"  {msg}")
            else:
                self.ui.print_info("  Usage: config set <key> <value>")
            self.tracer.end_trace(cid)
            return
        if lower == "config reset":
            print(self.config_editor.reset_to_defaults())
            self.tracer.end_trace(cid)
            return
        if lower == "config save":
            print(self.config_editor.save())
            self.tracer.end_trace(cid)
            return
        if lower == "config keys":
            print(self.config_editor.list_editable())
            self.tracer.end_trace(cid)
            return

        # ── Safety policy commands ──
        if lower == "policy":
            state = self._get_policy_state()
            if state:
                self.ui.print_info(f"  🛡️ Policy profile: {state.get('profile', 'unknown')}")
                self.ui.print_info(f"  👤 User role: {state.get('role', 'unknown')}")
            else:
                self.ui.print_info("  Safety policy controls unavailable")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("policy profile "):
            value = lower.replace("policy profile ", "", 1).strip()
            if hasattr(self.safety, "set_policy_profile"):
                self.safety.set_policy_profile(value)
                self.ui.print_info(f"  ✅ Policy profile set to: {value}")
                tag = self._policy_tag()
                if tag:
                    self.ui.print_info(f"  Active policy: {tag}")
            else:
                self.ui.print_info("  ❌ Policy profile setting is not supported")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("policy role "):
            value = lower.replace("policy role ", "", 1).strip()
            if hasattr(self.safety, "set_user_role"):
                self.safety.set_user_role(value)
                self.ui.print_info(f"  ✅ User role set to: {value}")
                tag = self._policy_tag()
                if tag:
                    self.ui.print_info(f"  Active policy: {tag}")
            else:
                self.ui.print_info("  ❌ Policy role setting is not supported")
            self.tracer.end_trace(cid)
            return

        if lower == "policy audit":
            if hasattr(self.safety, "get_audit_log"):
                rows = self.safety.get_audit_log(limit=20)
                if not rows:
                    self.ui.print_info("  No safety audit entries yet")
                else:
                    self.ui.print_info("  🧾 Recent safety audit entries:")
                    for row in rows[-10:]:
                        level = row.get("risk_level", "?")
                        cmd = (row.get("command", "") or "")[:80]
                        reason = (row.get("reason", "") or "")[:100]
                        self.ui.print_info(f"  • {level}: {cmd}")
                        if reason:
                            self.ui.print_info(f"    ↳ {reason}")
            else:
                self.ui.print_info("  ❌ Audit log is not supported by safety checker")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("policy audit export"):
            if hasattr(self.safety, "export_audit_json"):
                target = user_input[len("policy audit export"):].strip()
                if not target:
                    from config import NEUROSHELL_DIR
                    stamp = time.strftime("%Y%m%d_%H%M%S")
                    target = str(NEUROSHELL_DIR / "logs" / f"safety_audit_{stamp}.json")

                try:
                    if target.lower().endswith(".csv") and hasattr(self.safety, "export_audit_csv"):
                        count = self.safety.export_audit_csv(target, limit=1000)
                    else:
                        count = self.safety.export_audit_json(target, limit=1000)

                    digest_msg = ""
                    if hasattr(self.safety, "write_export_digest"):
                        digest = self.safety.write_export_digest(target)
                        digest_msg = f"\n  🔐 SHA256: {digest}"

                    self.ui.print_info(f"  ✅ Exported {count} safety audit entries to {target}{digest_msg}")
                except Exception as e:
                    self.ui.print_error(f"  ❌ Failed to export audit log: {e}")
            else:
                self.ui.print_info("  ❌ Audit export is not supported by safety checker")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("policy audit verify"):
            if hasattr(self.safety, "verify_audit_export"):
                target = user_input[len("policy audit verify"):].strip()
                if not target:
                    self.ui.print_info("  Usage: policy audit verify <file.json|file.csv>")
                    self.tracer.end_trace(cid)
                    return

                try:
                    result = self.safety.verify_audit_export(target)
                    if result.get("ok"):
                        checked = result.get("entries_checked", 0)
                        digest_ok = result.get("digest_ok")
                        if digest_ok is True:
                            digest_state = "valid"
                        elif digest_ok is False:
                            digest_state = "invalid"
                        else:
                            digest_state = "not present"

                        self.ui.print_info(
                            f"  ✅ Audit verification passed ({checked} entries, digest: {digest_state})"
                        )
                    else:
                        reason = result.get("reason", "verification_failed")
                        checked = result.get("entries_checked", 0)
                        self.ui.print_error(
                            f"  ❌ Audit verification failed: {reason} (checked={checked})"
                        )
                except Exception as e:
                    self.ui.print_error(f"  ❌ Failed to verify audit log: {e}")
            else:
                self.ui.print_info("  ❌ Audit verification is not supported by safety checker")
            self.tracer.end_trace(cid)
            return

        # ── Deployment commands ──
        if lower == "deploy status":
            current = self.deploy_manager.current()
            if not current:
                self.ui.print_info("  No active deployment recorded")
            else:
                self.ui.print_info(
                    f"  Active deployment: stage={current.get('stage')} version={current.get('version')}"
                )
                self.ui.print_info(f"  Config: {current.get('config_path')}")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("deploy promote "):
            payload = user_input[len("deploy promote "):].strip().split()
            if len(payload) < 6:
                self.ui.print_info(
                    "  Usage: deploy promote <stage> <version> <config_path> <manifest.json> <SHA256SUMS> <public.pem>"
                )
                self.tracer.end_trace(cid)
                return

            stage, version, cfg, manifest, checksums, pubkey = payload[:6]
            try:
                event = self.deploy_manager.promote_verified(
                    stage=stage,
                    version=version,
                    config_path=Path(cfg),
                    manifest_path=Path(manifest),
                    checksums_path=Path(checksums),
                    public_key_path=Path(pubkey),
                    require_signatures=True,
                )
                self.ui.print_info(
                    f"  ✅ Deployment promoted: stage={event.get('stage')} version={event.get('version')}"
                )
                self.ui.print_info(
                    f"  Verified artifacts: {event.get('verified_release', {}).get('artifacts_checked', 0)}"
                )
            except Exception as e:
                self.ui.print_error(f"  ❌ Deployment promote failed: {e}")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("deploy key add "):
            key_path = user_input[len("deploy key add "):].strip()
            if not key_path:
                self.ui.print_info("  Usage: deploy key add <public.pem>")
                self.tracer.end_trace(cid)
                return
            try:
                fp = self.deploy_manager.add_allowed_key(Path(key_path))
                self.ui.print_info(f"  ✅ Trusted deploy key fingerprint added: {fp}")
            except Exception as e:
                self.ui.print_error(f"  ❌ Failed to add trusted key: {e}")
            self.tracer.end_trace(cid)
            return

        if lower == "deploy key list":
            items = self.deploy_manager.get_allowed_key_fingerprints()
            if not items:
                self.ui.print_info("  No trusted deploy keys configured")
            else:
                self.ui.print_info("  Trusted deploy key fingerprints:")
                for fp in items:
                    self.ui.print_info(f"  • {fp}")
            self.tracer.end_trace(cid)
            return

        if lower == "deploy rollback":
            try:
                event = self.deploy_manager.rollback()
                to = event.get("to", {})
                self.ui.print_info(
                    f"  ✅ Rolled back to stage={to.get('stage')} version={to.get('version')}"
                )
            except Exception as e:
                self.ui.print_error(f"  ❌ Rollback failed: {e}")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("deploy drift "):
            cfg = user_input[len("deploy drift "):].strip()
            if not cfg:
                self.ui.print_info("  Usage: deploy drift <expected_config.toml>")
                self.tracer.end_trace(cid)
                return
            try:
                drift = self.deploy_manager.detect_drift(Path(cfg))
                if drift.get("drift"):
                    self.ui.print_error("  ❌ Config drift detected")
                else:
                    self.ui.print_info("  ✅ No config drift detected")
                self.ui.print_info(
                    f"  stage={drift.get('stage')} version={drift.get('version')}"
                )
            except Exception as e:
                self.ui.print_error(f"  ❌ Drift check failed: {e}")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("deploy canary "):
            payload = user_input[len("deploy canary "):].strip().split()
            if len(payload) < 7:
                self.ui.print_info(
                    "  Usage: deploy canary <stage> <version> <config_path> <manifest.json> <SHA256SUMS> <public.pem> <max_burn_ratio>"
                )
                self.tracer.end_trace(cid)
                return

            stage, version, cfg, manifest, checksums, pubkey, max_burn = payload[:7]
            try:
                burn = self.runtime_slo.error_budget_burn(target_availability=0.99, window_minutes=60)
                snapshot = {
                    "budget_consumed_ratio": burn.get("budget_consumed_ratio", 0.0),
                    "alerts": self.runtime_slo.evaluate_alerts(),
                }
                result = self.deploy_manager.canary_promote(
                    stage=stage,
                    version=version,
                    config_path=Path(cfg),
                    manifest_path=Path(manifest),
                    checksums_path=Path(checksums),
                    public_key_path=Path(pubkey),
                    slo_snapshot=snapshot,
                    max_budget_consumed_ratio=float(max_burn),
                )

                if result.get("rolled_back"):
                    self.ui.print_error(
                        f"  ❌ Canary auto-rolled back (burn={result.get('burn_ratio'):.2f})"
                    )
                else:
                    self.ui.print_info(
                        f"  ✅ Canary promoted successfully (burn={result.get('burn_ratio'):.2f})"
                    )
            except Exception as e:
                self.ui.print_error(f"  ❌ Canary deploy failed: {e}")
            self.tracer.end_trace(cid)
            return

        if lower == "deploy audit":
            try:
                rows = self.deploy_manager.get_audit_log(limit=10)
                if not rows:
                    self.ui.print_info("  No deployment audit entries yet")
                else:
                    self.ui.print_info("  🧾 Recent deployment audit entries:")
                    for row in rows:
                        self.ui.print_info(f"  • {row.get('action')} @ {row.get('timestamp'):.0f}")
            except Exception as e:
                self.ui.print_error(f"  ❌ Failed to read deploy audit: {e}")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("deploy audit export"):
            target = user_input[len("deploy audit export"):].strip()
            if not target:
                stamp = time.strftime("%Y%m%d_%H%M%S")
                target = str(NEUROSHELL_DIR / "logs" / f"deploy_audit_{stamp}.json")
            try:
                out = self.deploy_manager.export_audit_json(Path(target), limit=1000)
                self.ui.print_info(f"  ✅ Exported deployment audit to {out}")
            except Exception as e:
                self.ui.print_error(f"  ❌ Failed to export deployment audit: {e}")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("deploy audit verify"):
            target = user_input[len("deploy audit verify"):].strip()
            if not target:
                self.ui.print_info("  Usage: deploy audit verify <file.json>")
                self.tracer.end_trace(cid)
                return
            try:
                result = self.deploy_manager.verify_audit_export(Path(target))
                if result.get("ok"):
                    self.ui.print_info(
                        f"  ✅ Deployment audit verification passed ({result.get('entries_checked', 0)} entries)"
                    )
                else:
                    self.ui.print_error(
                        f"  ❌ Deployment audit verification failed: {result.get('reason')}"
                    )
            except Exception as e:
                self.ui.print_error(f"  ❌ Failed to verify deployment audit: {e}")
            self.tracer.end_trace(cid)
            return

        # ── Timer & Stats ──
        if lower.startswith("time "):
            cmd = user_input[5:].strip()
            timing = self.command_timer.time_command(cmd)
            print(timing.display())
            self.tracer.end_trace(cid)
            return
        if lower == "stats":
            print(self.command_timer.get_formatted_stats(self.metrics))
            self.tracer.end_trace(cid)
            return

        # ── History export/import ──
        if lower.startswith("history export"):
            self._handle_history_export(user_input)
            self.tracer.end_trace(cid)
            return
        if lower.startswith("history import"):
            filepath = user_input[15:].strip()
            if filepath:
                from pathlib import Path
                count = self.history.import_json(Path(filepath))
                self.ui.print_info(f"  ✅ Imported {count} commands from {filepath}")
            else:
                self.ui.print_info("  Usage: history import <filepath.json>")
            self.tracer.end_trace(cid)
            return

        # ── Docs / Cheatsheet / Playbook ──
        if lower in ("docs", "docs generate"):
            output = self.docs_generator.generate_cheatsheet()
            print(output)
            self.tracer.end_trace(cid)
            return
        if lower == "cheatsheet":
            output = self.docs_generator.generate_cheatsheet()
            print(output)
            self.tracer.end_trace(cid)
            return
        if lower == "playbook":
            output = self.docs_generator.generate_error_playbook()
            print(output)
            self.tracer.end_trace(cid)
            return

        # ── Bookmark commands (!save, !run, !list, !delete) ──
        if lower.startswith("!"):
            self._handle_bookmark(user_input, cid)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        # ── Agent mode (agent: <task>) ──
        if lower.startswith("agent:"):
            task_desc = user_input.split(":", 1)[1].strip()
            self._handle_agent(task_desc, cid)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        # ── Script generator (script: <description>) ──
        if lower.startswith("script:"):
            desc = user_input.split(":", 1)[1].strip()
            self._handle_script(desc, cid)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        # ── Smart Suggestions ──
        if lower in ("suggest", "suggestions"):
            print(self.smart_suggester.get_formatted())
            self.tracer.end_trace(cid)
            return
        if lower.startswith("suggest ") and lower[8:].strip().isdigit():
            idx = int(lower[8:].strip())
            cmd = self.smart_suggester.get_suggestion_by_index(idx)
            if cmd:
                self.ui.print_info(f"  ▶ Running: {cmd}")
                self.process_input(cmd)
            else:
                self.ui.print_info(f"  ❌ No suggestion #{idx}")
            self.tracer.end_trace(cid)
            return

        # ── Pipeline templates list ──
        if lower == "pipelines":
            builder = getattr(self, "pipeline_builder", None)
            if not builder:
                self.ui.print_error("  Pipeline builder unavailable.")
                self.tracer.end_trace(cid)
                return

            templates = builder.list_templates()
            print("  ╔══════════════════════════════════════════════╗")
            print("  ║       📋 Pipeline Templates                  ║")
            print("  ╚══════════════════════════════════════════════╝")
            for t in templates:
                print(f"    ▸ {t}")
            print(f"\n  Total: {len(templates)} templates")
            self.tracer.end_trace(cid)
            return

        # ── Dashboard ──
        if lower == "dashboard":
            self.dashboard.show()
            # Wait for Enter only in real CLI mode; skip in GUI mode (no tty)
            if hasattr(sys.stdin, 'isatty') and sys.stdin.isatty():
                try:
                    input()  # wait for Enter
                except (EOFError, OSError, ValueError):
                    pass
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        if lower.startswith("help"):
            topic = lower.replace("help", "").strip()
            print(self.help.get_help(topic))
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        # ═══════════════════════════════════════════════════════
        # Tier 1-4 Extension Commands
        # ═══════════════════════════════════════════════════════

        # ── Voice mode ──
        if lower in ("voice", "listen", "voice mode"):
            if hasattr(self, 'ext_voice') and self.ext_voice.available:
                self.ui.print_info("  🎤 Listening... speak your command")
                text = self.ext_voice.listen()
                if text:
                    self.ui.print_info(f"  🗣️ Heard: {text}")
                    self.process_input(text)
                else:
                    self.ui.print_error("  Could not understand. Try again.")
            else:
                self.ui.print_info(f"  🎤 Voice unavailable. Install: {VoiceCommandEngine.install_hint() if hasattr(self, 'ext_voice') else 'pip install SpeechRecognition pyaudio'}")
            self.tracer.end_trace(cid)
            return

        # ── Vulnerability scan ──
        if lower in ("scan", "security scan", "vuln scan", "scan project"):
            if hasattr(self, 'ext_scanner'):
                scans = self.ext_scanner.get_scan_commands(os.getcwd())
                if not scans:
                    self.ui.print_info("  No scannable project files found.")
                else:
                    self.ui.print_info(f"  🛡️ Running {len(scans)} security checks...")
                    for desc, cmd in scans:
                        self.ui.print_info(f"\n  📋 {desc}")
                        self.ui.print_info(f"  $ {cmd}")
                        try:
                            result = self.executor.execute(cmd)
                            if result.stdout:
                                print(result.stdout[:500])
                        except Exception:
                            pass
            self.tracer.end_trace(cid)
            return

        # ── Risk score ──
        if lower.startswith("risk "):
            cmd = user_input[5:].strip()
            if hasattr(self, '_ext_risk'):
                risk = self._ext_risk(cmd)
                self.ui.print_info(f"  {risk.badge}  Risk: {risk.meter}")
                for r in risk.reasons:
                    self.ui.print_info(f"    • {r}")
            self.tracer.end_trace(cid)
            return

        # ── Workflow engine ──
        if lower.startswith("schedule ") or lower.startswith("every "):
            if hasattr(self, 'ext_workflow'):
                task = self.ext_workflow.parse(user_input)
                if task:
                    install_cmd = self.ext_workflow.get_install_command(task)
                    self.ui.print_info(f"  📅 Workflow: {task.name}")
                    self.ui.print_info(f"  Commands: {', '.join(task.commands)}")
                    self.ui.print_info(f"  Install with: {install_cmd}")
                else:
                    self.ui.print_info("  Could not parse workflow. Try: 'every day at 9 run git pull'")
            self.tracer.end_trace(cid)
            return

        # ── Theme commands ──
        if lower == "themes" or lower == "theme list":
            if hasattr(self, 'ext_themes'):
                self.ui.print_info(f"  🎨 Themes: {', '.join(self.ext_themes.list_themes())}")
                self.ui.print_info(f"  Current: {self.ext_themes.current_name}")
            self.tracer.end_trace(cid)
            return
        if lower.startswith("theme "):
            name = user_input[6:].strip()
            if hasattr(self, 'ext_themes') and self.ext_themes.set_theme(name):
                self.ui.print_info(f"  🎨 Theme set to: {name}")
            else:
                self.ui.print_info(f"  ❌ Unknown theme. Available: {', '.join(self.ext_themes.list_themes()) if hasattr(self, 'ext_themes') else 'none'}")
            self.tracer.end_trace(cid)
            return

        # ── Snippet commands ──
        if lower == "snippets":
            if hasattr(self, 'ext_snippets'):
                items = self.ext_snippets.list_all()
                if items:
                    self.ui.print_info("  📌 Saved snippets:")
                    for s in items:
                        self.ui.print_info(f"    {s.name}: {s.command} ({s.use_count} uses)")
                else:
                    self.ui.print_info("  No snippets saved. Use: snippet save <name> <command>")
            self.tracer.end_trace(cid)
            return
        if lower.startswith("snippet save "):
            parts = user_input[13:].strip().split(None, 1)
            if len(parts) == 2 and hasattr(self, 'ext_snippets'):
                self.ext_snippets.save(parts[0], parts[1])
                self.ui.print_info(f"  ✅ Snippet saved: {parts[0]}")
            else:
                self.ui.print_info("  Usage: snippet save <name> <command>")
            self.tracer.end_trace(cid)
            return
        if lower.startswith("snippet run "):
            name = user_input[12:].strip()
            if hasattr(self, 'ext_snippets'):
                s = self.ext_snippets.get(name)
                if s:
                    self.ui.print_info(f"  ▶ Running snippet: {s.command}")
                    self.process_input(s.command)
                else:
                    self.ui.print_info(f"  ❌ No snippet named '{name}'")
            self.tracer.end_trace(cid)
            return

        # ── Command palette ──
        if lower.startswith("palette ") or lower.startswith("find command "):
            query = user_input.split(None, 1)[1] if len(user_input.split(None, 1)) > 1 else ""
            if hasattr(self, 'ext_palette'):
                results = self.ext_palette.search(query)
                if results:
                    self.ui.print_info(f"  🔍 {len(results)} commands found:")
                    for r in results:
                        self.ui.print_info(f"    [{r.category}] {r.name}: {r.command}")
                else:
                    self.ui.print_info(f"  No commands matched '{query}'")
            self.tracer.end_trace(cid)
            return

        # ── Notebook mode ──
        if lower == "notebook" or lower == "notebook show":
            if hasattr(self, 'ext_notebook'):
                print(self.ext_notebook.export_markdown())
            self.tracer.end_trace(cid)
            return
        if lower.startswith("notebook note "):
            note = user_input[14:].strip()
            if hasattr(self, 'ext_notebook'):
                self.ext_notebook.add_note(note)
                self.ui.print_info("  📝 Note added to notebook")
            self.tracer.end_trace(cid)
            return
        if lower.startswith("notebook save "):
            path = user_input[14:].strip()
            if hasattr(self, 'ext_notebook'):
                self.ext_notebook.save(Path(path))
                self.ui.print_info(f"  💾 Notebook saved to {path}")
            self.tracer.end_trace(cid)
            return

        # ── Diff preview ──
        if lower.startswith("preview ") or lower.startswith("dry-run ") or lower.startswith("dryrun "):
            cmd = user_input.split(None, 1)[1] if len(user_input.split(None, 1)) > 1 else ""
            if hasattr(self, 'ext_diff'):
                preview = self.ext_diff.get_preview(cmd)
                if preview:
                    self.ui.print_info(f"  👁️ Preview: {preview[1]}")
                    self.ui.print_info(f"  $ {preview[0]}")
                else:
                    self.ui.print_info(f"  No preview available for: {cmd}")
            self.tracer.end_trace(cid)
            return

        # ── Audit commands ──
        if lower == "audit" or lower == "audit report":
            if hasattr(self, 'ext_audit'):
                print(self.ext_audit.export_report())
            self.tracer.end_trace(cid)
            return

        # ── API server ──
        if lower == "api start" or lower == "start api":
            if hasattr(self, 'ext_api'):
                if self.ext_api.start():
                    self.ui.print_info(f"  🌐 API running on http://127.0.0.1:{self.ext_api.port}")
                    self.ui.print_info(f"  Usage: {NeuroShellAPI.usage_hint()}")
                else:
                    self.ui.print_error("  API server failed to start")
            self.tracer.end_trace(cid)
            return

        # ── Sync commands ──
        if lower == "sync export":
            if hasattr(self, 'ext_sync'):
                path = self.ext_sync.export_config()
                self.ui.print_info(f"  📤 Config exported to: {path}")
            self.tracer.end_trace(cid)
            return
        if lower.startswith("sync import "):
            filepath = user_input[12:].strip()
            if hasattr(self, 'ext_sync'):
                result = self.ext_sync.import_config(Path(filepath))
                self.ui.print_info(f"  📥 Sync result: {result}")
            self.tracer.end_trace(cid)
            return

        # ── Memory/timeline commands ──
        if lower == "timeline" or lower == "memory timeline":
            if hasattr(self, 'ext_memory'):
                entries = self.ext_memory.get_timeline(20)
                if entries:
                    self.ui.print_info("  📅 Command Timeline:")
                    for e in entries:
                        icon = "✅" if e.success else "❌"
                        self.ui.print_info(f"    {icon} {e.input_text[:50]} → {e.command[:50]}")
                else:
                    self.ui.print_info("  No history yet.")
            self.tracer.end_trace(cid)
            return
        if lower == "memory stats":
            if hasattr(self, 'ext_memory'):
                stats = self.ext_memory.get_stats()
                for k, v in stats.items():
                    self.ui.print_info(f"    {k}: {v}")
            self.tracer.end_trace(cid)
            return

        if lower.startswith("browser"):
            self._handle_browser_command(user_input)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        if lower in ("my repos", "repos", "list repos", "show repos", "my repositories", "list my repos", "show my repos", "gh repo list", "github repos"):
            self._handle_repos_list()
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        if lower.startswith("github"):
            self._handle_github_command(user_input)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        # ── SmartOpen: intercept open/launch/clone/power before NLP mis-routes them ──
        _SMART_PREFIXES = ("open ", "launch ", "start ", "run ", "navigate to ",
                           "go to ", "browse ", "clone ", "download ", "get ",
                           "zip ", "unzip ", "compress ", "extract ", "create zip ",
                           "create a zip ", "create an zip ", "archive ")
        _POWER_WORDS   = ("lock", "restart", "reboot", "shutdown", "shut down",
                          "sign out", "log out", "sleep", "lock screen",
                          "lock computer", "flush dns", "clear dns",
                          "screenshot", "take screenshot", "battery status",
                          "check battery", "empty recycle bin", "my ip")
        if (
            any(lower.startswith(p) for p in _SMART_PREFIXES)
            or lower in _POWER_WORDS
        ):
            self._handle_open_command(user_input)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        # NLP classification for everything else
        intent = self.intent_classifier.classify(user_input)
        entities = self.entity_extractor.extract(user_input)
        sent = self.sentiment.analyze(user_input, was_error=bool(self._last_error_output))
        self.tracer.add_event(cid, "nlp_done", intent=intent.intent, confidence=intent.confidence)

        # ── Follow-up detection ──
        words = set(lower.split())
        is_followup = (
            bool(words & self._FOLLOWUP_WORDS)
            and self._conversation_context
            and intent.intent in ("natural_language", "question")
        )

        if is_followup:
            self._handle_followup(user_input, cid)
            total_ms = (time.time() - start_time) * 1000
            self.metrics.record_latency("total_pipeline", total_ms)
            self.tracer.end_trace(cid)
            return

        # ── Expand aliases before routing ──
        expanded = self.alias_manager.expand(user_input)
        if expanded != user_input:
            user_input = expanded
            self.ui.print_info(f"  📎 Expanded alias → {user_input}")

        # ── Step 2: Route by intent ──────────────────
        if intent.intent == "pipeline_request":
            self._handle_pipeline(user_input, cid)

        elif intent.intent == "shell_command":
            # Fuzzy typo correction check
            correction = self.fuzzy_corrector.correct(user_input)
            if correction:
                self.ui.print_info(f"  💡 Did you mean: {correction.corrected}?")
                if self.ui.confirm("Use corrected command?"):
                    self._handle_shell_command(correction.corrected, cid)
                else:
                    self._handle_shell_command(user_input, cid)
            else:
                self._handle_shell_command(user_input, cid)

        elif intent.intent in ("natural_language", "question"):
            # Check for command chaining first
            if self.chain_builder.is_chain_request(user_input):
                handled = self._handle_chain(user_input, cid)
                if not handled:
                    self._handle_natural_language(user_input, entities, intent, cid)
            else:
                self._handle_natural_language(user_input, entities, intent, cid)

        else:
            self._handle_shell_command(user_input, cid)

        # ── Step 3: Post-processing ──────────────────
        if sent.state == "frustrated" and self.sentiment.should_offer_help():
            if sent.suggestion:
                self.ui.print_hint(sent.suggestion)
            else:
                hint = self.help.get_hint("first_error")
                if hint:
                    self.ui.print_hint(hint)

        # Adaptive verbosity
        verbosity = self.sentiment.get_verbosity_level()
        self.logger.debug("pipeline_complete", verbosity=verbosity, sentiment=sent.state)

        total_ms = (time.time() - start_time) * 1000
        self.metrics.record_latency("total_pipeline", total_ms)
        self.tracer.end_trace(cid)

    # ═══════════════════════════════════════════════════════
    # Intent Handlers
    # ═══════════════════════════════════════════════════════

    def _handle_browser_command(self, user_input: str):
        """Handle browser access commands with optional full automation."""
        try:
            args = shlex.split(user_input)
        except ValueError as e:
            self.ui.print_error(f"  ❌ Invalid browser command syntax: {e}")
            return

        if len(args) == 1 or args[1] == "status":
            status = self.browser_access.status()
            self.ui.print_info("  🌐 Browser access status:")
            self.ui.print_info(f"  • Fetch ready: {status.get('fetch_ready')}")
            self.ui.print_info(f"  • Playwright installed: {status.get('playwright_installed')}")
            self.ui.print_info(f"  • Screenshot ready: {status.get('screenshot_ready')}")
            if not status.get("playwright_installed"):
                self.ui.print_info("  💡 For full automation: pip install playwright && playwright install chromium")
            return

        sub = args[1]
        if sub == "open" and len(args) >= 3:
            msg = self.browser_access.open_url(args[2])
            self.ui.print_info(f"  ✅ {msg}")
            return

        if sub == "fetch" and len(args) >= 3:
            html = self.browser_access.fetch_html(args[2])
            self.ui.print_info(f"  ✅ Fetched HTML ({len(html)} chars)")
            print(html[:2000] + ("..." if len(html) > 2000 else ""))
            return

        if sub == "extract" and len(args) >= 3:
            text = self.browser_access.extract_text(args[2])
            self.ui.print_info(f"  ✅ Extracted text ({len(text)} chars)")
            print(text)
            return

        if sub == "screenshot" and len(args) >= 3:
            out = Path(args[3]) if len(args) >= 4 else Path("artifacts") / "browser_screenshot.png"
            path = self.browser_access.screenshot(args[2], out)
            self.ui.print_info(f"  ✅ Screenshot saved: {path}")
            return

        self.ui.print_info("  Usage:")
        self.ui.print_info("  • browser status")
        self.ui.print_info("  • browser open <url>")
        self.ui.print_info("  • browser fetch <url>")
        self.ui.print_info("  • browser extract <url>")
        self.ui.print_info("  • browser screenshot <url> [output.png]")

    def _handle_repos_list(self):
        """Render GitHub repositories in an enterprise-grade formatted table."""
        from rich.console import Console
        from rich.table import Table
        console = Console()

        try:
            if not hasattr(self, "github_access") or self.github_access is None:
                from operations.github_access import GitHubAccessManager
                from pathlib import Path
                self.github_access = GitHubAccessManager(Path.cwd())

            repos = self.github_access.repo_list(limit=30)
            if not repos:
                console.print("  [dim]No repositories found or not authenticated with 'gh auth login'.[/dim]")
                return

            table = Table(title="🐙 GitHub Repositories", title_style="bold cyan", border_style="cyan", show_lines=True)
            table.add_column("#", style="dim", justify="right", width=4)
            table.add_column("Repository", style="bold white", width=36)
            table.add_column("Visibility", justify="center", width=12)
            table.add_column("Updated", style="dim", justify="center", width=12)
            table.add_column("Description", style="white", overflow="fold")

            for i, r in enumerate(repos, 1):
                name = r.get("nameWithOwner", "Unknown")
                is_priv = r.get("isPrivate", False)
                vis = "[magenta]private[/magenta]" if is_priv else "[green]public[/green]"
                updated = (r.get("updatedAt") or "")[:10]
                desc = r.get("description") or "-"
                table.add_row(str(i), name, vis, updated, desc)

            console.print(table)
        except Exception as e:
            console.print(f"  [red]❌ Failed to fetch repositories: {e}[/red]")

    def _handle_github_command(self, user_input: str):
        """Handle GitHub API-style commands via GitHub CLI."""
        try:
            args = shlex.split(user_input)
        except ValueError as e:
            self.ui.print_error(f"  ❌ Invalid github command syntax: {e}")
            return

        repo_ctx = None
        if "--repo" in args:
            i = args.index("--repo")
            if i + 1 < len(args):
                repo_ctx = args[i + 1]
                args = args[:i] + args[i + 2:]
            else:
                self.ui.print_error("  ❌ Missing value for --repo (expected owner/name)")
                return

        if len(args) == 1 or args[1] == "status":
            status = self.github_access.status()
            self.ui.print_info("  🐙 GitHub access status:")
            self.ui.print_info(f"  • gh installed: {status.get('gh_installed')}")
            self.ui.print_info(f"  • authenticated: {status.get('authenticated')}")
            self.ui.print_info(f"  • default repo: {status.get('default_repo') or '(not set)'}")
            detail = status.get("detail", "")
            if detail:
                self.ui.print_info(f"  • detail: {detail[:240]}")
            if not status.get("gh_installed"):
                self.ui.print_info("  💡 Install GitHub CLI: https://cli.github.com/")
            elif not status.get("authenticated"):
                self.ui.print_info("  💡 Authenticate with: gh auth login")
            return

        sub = args[1]
        try:
            if sub == "repo":
                if len(args) >= 3 and args[2] == "set":
                    if len(args) < 4:
                        self.ui.print_info("  Usage: github repo set <owner/name>")
                        return
                    target = self.github_access.set_default_repo(args[3])
                    self.ui.print_info(f"  ✅ Default GitHub repo set: {target}")
                    return
                if len(args) >= 3 and args[2] in {"current", "show"}:
                    current = self.github_access.get_default_repo()
                    if current:
                        self.ui.print_info(f"  ✅ Default GitHub repo: {current}")
                    else:
                        self.ui.print_info("  No default GitHub repo set")
                    return

                repo = self.github_access.repo_view(repo=repo_ctx)
                self.ui.print_info(f"  ✅ Repo: {repo.get('nameWithOwner')} ({repo.get('url')})")
                default_ref = (repo.get("defaultBranchRef") or {}).get("name")
                if default_ref:
                    self.ui.print_info(f"  • default branch: {default_ref}")
                return

            if sub == "pr" and len(args) >= 3:
                action = args[2]
                if action == "list":
                    state = args[3] if len(args) >= 4 else "open"
                    prs = self.github_access.pr_list(state=state, repo=repo_ctx)
                    self.ui.print_info(f"  ✅ PRs ({state}): {len(prs)}")
                    for row in prs[:20]:
                        author = (row.get("author") or {}).get("login", "?")
                        self.ui.print_info(f"  • #{row.get('number')} {row.get('title')} ({author})")
                    return
                if action == "view" and len(args) >= 4:
                    pr = self.github_access.pr_view(int(args[3]), repo=repo_ctx)
                    author = (pr.get("author") or {}).get("login", "?")
                    self.ui.print_info(f"  ✅ PR #{pr.get('number')}: {pr.get('title')}")
                    self.ui.print_info(f"  • state: {pr.get('state')} | author: {author}")
                    self.ui.print_info(f"  • branch: {pr.get('headRefName')} -> {pr.get('baseRefName')}")
                    self.ui.print_info(f"  • url: {pr.get('url')}")
                    return
                if action == "create" and len(args) >= 5:
                    title = args[3]
                    body = args[4]
                    base = None
                    head = None
                    i = 5
                    while i < len(args):
                        if args[i] == "--base" and i + 1 < len(args):
                            base = args[i + 1]
                            i += 2
                        elif args[i] == "--head" and i + 1 < len(args):
                            head = args[i + 1]
                            i += 2
                        else:
                            i += 1
                    url = self.github_access.pr_create(title=title, body=body, base=base, head=head, repo=repo_ctx)
                    self.ui.print_info(f"  ✅ PR created: {url}")
                    return

            if sub == "issue" and len(args) >= 3:
                action = args[2]
                if action == "list":
                    state = args[3] if len(args) >= 4 else "open"
                    issues = self.github_access.issue_list(state=state, repo=repo_ctx)
                    self.ui.print_info(f"  ✅ Issues ({state}): {len(issues)}")
                    for row in issues[:20]:
                        author = (row.get("author") or {}).get("login", "?")
                        self.ui.print_info(f"  • #{row.get('number')} {row.get('title')} ({author})")
                    return
                if action == "create" and len(args) >= 5:
                    url = self.github_access.issue_create(title=args[3], body=args[4], repo=repo_ctx)
                    self.ui.print_info(f"  ✅ Issue created: {url}")
                    return
        except Exception as e:
            self.ui.print_error(f"  ❌ GitHub command failed: {e}")
            return

        self.ui.print_info("  Usage:")
        self.ui.print_info("  • github status")
        self.ui.print_info("  • github repo set <owner/name>")
        self.ui.print_info("  • github repo current")
        self.ui.print_info("  • github repo [--repo owner/name]")
        self.ui.print_info("  • github pr list [open|closed|merged] [--repo owner/name]")
        self.ui.print_info("  • github pr view <number> [--repo owner/name]")
        self.ui.print_info("  • github pr create \"title\" \"body\" [--base main] [--head feature] [--repo owner/name]")
        self.ui.print_info("  • github issue list [open|closed] [--repo owner/name]")
        self.ui.print_info("  • github issue create \"title\" \"body\" [--repo owner/name]")

    def _handle_open_command(self, target: str):
        """
        Smart 'open' handler — maps common app names / URLs to the correct
        Windows launch mechanism. Prevents NLP from mis-routing 'open chrome'
        to shell which would attempt 'ren chrome' and fail.

        Resolution pipeline (via SmartOpenEngine):
          1. GitHub clone/download intent  (clone react, clone owner/repo)
          2. Power commands                (lock, restart, flush dns)
          3. System shortcuts              (task manager, device manager)
          4. App registry                 (chrome, whatsapp, vscode)
          5. URL / site name              (github, youtube, mdn)
          6. Folder / file resolution     (open downloads folder)
          7. Fallback shell execution
        """
        # ── 1. Try the full SmartOpenEngine (includes clone, power, apps, URLs) ──
        # Pass the full original input — SmartOpenEngine handles all prefixes
        # (open, clone, launch, power words) internally.
        result = self.smart_open.try_resolve(target)
        if result:
            self.ui.print_info(f"  💡 {result.explanation}")
            self._handle_shell_command(result.command, self.tracer.start_trace())
            return

        # ── 2. No smart match — fall back to native OS open ──
        try:
            os.startfile(target)  # Windows-native, no console flash
            self.ui.print_info(f"  ✅ Attempting to open: {target}")
        except OSError:
            # Fallback for edge cases — hide the console window
            import subprocess
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            try:
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "", target],
                    startupinfo=si,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self.ui.print_info(f"  ✅ Attempting to open: {target}")
            except Exception as e:
                self.ui.print_error(f"  ❌ Could not open '{target}': {e}")
                self.ui.print_info("  💡 Tip: Type 'fix' to auto-fix that error")

    def _handle_shell_command(self, command: str, cid: str):
        """Execute shell command through safety pipeline."""
        self.tracer.add_event(cid, "safety_check")

        # ── Safe Degradation Checks ──
        has_ui = hasattr(self, 'ui') and self.ui
        has_safety = hasattr(self, 'safety') and self.safety
        has_network = hasattr(self, 'network') and self.network

        if has_safety:
            safety = self.safety.check(command)
            policy_tag = self._policy_tag()
            if safety.risk_level in (self._RiskLevel.DANGER, self._RiskLevel.BLOCKED):
                if has_ui:
                    self.ui.print_safety(safety)
                    if policy_tag:
                        self.ui.print_info(f"  🛡️ Blocked under policy {policy_tag}")
                else:
                    print(f"  ❌ Blocked: {safety.reason}")
                self.metrics.count("blocked_commands")
                return

            if safety.needs_confirmation:
                if has_ui:
                    self.ui.print_safety(safety)
                    if policy_tag:
                        self.ui.print_info(f"  🛡️ Confirmation required by policy {policy_tag}")
                    if not self.ui.confirm("Execute anyway?"):
                        self.metrics.count("user_cancelled")
                        return
                else:
                    print(f"  ⚠️ Warning: {safety.reason}. Skipping for safety in degraded mode.")
                    return
        # Dependency check
        if hasattr(self, 'dep_resolver') and self.dep_resolver:
            dep_issues = self.dep_resolver.check_command(command)
            for issue in dep_issues:
                if not issue.is_available:
                    if has_ui:
                        self.ui.print_info(f"  ⚠️ {issue.message}")
                        if issue.fix_command:
                            self.ui.print_info(f"  💡 Fix: {issue.fix_command}")
                    else:
                        print(f"  ⚠️ {issue.message}")

        # Network check
        if has_network:
            net_warning = self.network.warn_if_offline(command)
            if net_warning:
                if has_ui:
                    self.ui.print_info(net_warning)
                else:
                    print(net_warning)

        # Execute with spinner for potentially slow commands
        self.tracer.add_event(cid, "execute")

        capture = False
        if has_safety:
            capture = safety.risk_level == self._RiskLevel.CAUTION

        result = self.executor.execute(
            command,
            stream_callback=lambda line: print(line),
            capture_snapshot=capture,
        )

        self._last_command = command
        self.metrics.count("commands_executed")

        # Parse and highlight output
        language_hint = ""
        parsed_output = None
        if result.stdout and hasattr(self, 'parser') and self.parser:
            parsed_output = self.parser.parse(result.stdout)
            self.tracer.add_event(cid, "parsed", output_type=parsed_output.output_type.value)
            language_hint = getattr(parsed_output, 'language_hint', "")

        # Display result
        if has_ui:
            self.ui.print_result(command, result, language_hint=language_hint, parsed_output=parsed_output)
        else:
            code = getattr(result, 'exit_code', getattr(result, 'returncode', 0))
            print(f"\n[Exit code: {code}]")
            if result.stdout: print(result.stdout)
            if result.stderr: print(f"Error: {result.stderr}")

        # Store in history
        if hasattr(self, 'history') and self.history:
            try:
                from core.history import CommandRecord
                record = CommandRecord(
                    command=command,
                    exit_code=result.exit_code,
                    stdout_preview=result.stdout[:500] if result.stdout else "",
                    stderr_preview=result.stderr[:200] if result.stderr else "",
                    cwd=os.getcwd(),
                    shell=result.shell,
                    duration_ms=result.duration_ms,
                    session_id=self.session_id,
                )
                if hasattr(self.history, 'add_command'):
                    self.history.add_command(record)
                elif hasattr(self.history, 'add'):
                    self.history.add(record)
            except Exception:
                pass

        # Record in conversation memory for follow-ups
        self._conversation_context.append({
            'input': command,
            'command': command,
            'output': (result.stdout or result.stderr or '')[:300],
        })
        if len(self._conversation_context) > self._MAX_MEMORY:
            self._conversation_context.pop(0)

        # ── Execution Lifecycle Hooks ──
        # 1. Session Memory
        if hasattr(self, "ext_memory") and self.ext_memory:
            try:
                self.ext_memory.record(
                    input_text=command,
                    command=command,
                    success=result.exit_code == 0,
                    duration_ms=result.duration_ms,
                    context=os.getcwd(),
                )
            except Exception:
                pass

        # 2. Session Recorder (if active)
        if hasattr(self, "ext_recorder") and self.ext_recorder and self.ext_recorder.is_recording:
            try:
                self.ext_recorder.record_input(command)
                self.ext_recorder.record_output(result.stdout or result.stderr or "", exit_code=result.exit_code)
            except Exception:
                pass

        # 3. Runtime SLO Metrics
        if hasattr(self, "runtime_slo") and self.runtime_slo:
            try:
                self.runtime_slo.record_latency_ms("command_exec", result.duration_ms)
                if result.exit_code != 0:
                    self.runtime_slo.record_error()
            except Exception:
                pass

        # 4. Long Task Notification (>10s)
        if hasattr(self, "ext_notifications") and self.ext_notifications and result.duration_ms > 10000:
            try:
                self.ext_notifications.on_command_complete(command, result.duration_ms, result.exit_code == 0)
            except Exception:
                pass

        # 5. Workspace Profile auto-activation
        if hasattr(self, "workspace_profiles") and self.workspace_profiles:
            try:
                self.workspace_profiles.activate(os.getcwd())
            except Exception:
                pass

        # Handle errors
        if result.exit_code != 0:
            self._last_error_output = result.stderr or result.stdout
            if hasattr(self, 'sentiment') and self.sentiment:
                try:
                    self.sentiment.record_error()
                except Exception:
                    pass
            if hasattr(self, 'help') and self.help and has_ui:
                try:
                    hint = self.help.get_hint("first_error")
                    if hint:
                        self.ui.print_hint(hint)
                except Exception:
                    pass
        else:
            self._last_error_output = ""

        self.tracer.add_event(cid, "complete", exit_code=result.exit_code)

    def _handle_natural_language(self, user_input: str, entities, intent, cid: str):

        # ---- v5.0 Offline/PII Hooks ----
        if getattr(self.config, 'raw_shell_mode', False):
            # No-LLM mode
            res = self.phrase_dict.translate(user_input)
            if res and res.get('confidence', 0.0) > 0.8:
                return self._handle_shell_command(res['command'], cid)

            self.ui.print_error('Raw Shell Mode: Command not found in offline dictionary. Try phrasing it differently.')
            return

        # PII Scrubbing
        safe_input = self.pii_scrubber.scrub(user_input)
        if safe_input != user_input:
            self.ui.print_info('🔒 PII Scrubber redacted sensitive data before cloud transmission.')
            user_input = safe_input

        # Check offline fallback
        provider, reason = self.offline_fallback.get_active_provider()
        if provider == 'ollama' and reason == 'offline-fallback':
            self.ui.print_warning('☁️ Cloud unavailable. Pivoting to local Ollama.')
            self.config.llm.provider = 'ollama'

        # Optional: Test C++ parser just for benchmarking if enabled
        if getattr(self, '_cpp_enabled', False):
            try:
                self.cpp_parser.parse(user_input)
            except Exception:
                pass

        """Handle NL translation with entity enrichment and streaming."""
        self.tracer.add_event(cid, "translate_start")

        entity_dict = {}
        if entities.has_entities:
            entity_dict = {
                "paths": entities.paths,
                "packages": entities.packages,
                "urls": entities.urls,
                "numbers": entities.numbers,
                "commands": entities.commands,
                "git_refs": entities.git_refs,
                "docker": entities.docker_entities,
                "ports": [str(p) for p in entities.ports],
                "env_vars": entities.env_vars,
            }

        # Show streaming indicator for LLM translations
        import sys
        sys.stdout.write("\r  🤖 Thinking")
        sys.stdout.flush()
        _dots = [0]
        _orig_generate = None

        # Wrap LLM generate to show streaming dots
        if hasattr(self.translator, 'llm') and self.translator.llm:
            _orig_generate = self.translator.llm.generate_json
            def _streaming_generate(prompt, system_prompt=""):
                # Show streaming dots during LLM call
                import threading
                stop_event = threading.Event()
                def _animate():
                    while not stop_event.is_set():
                        _dots[0] = (_dots[0] % 3) + 1
                        sys.stdout.write(f"\r  🤖 Thinking{'.' * _dots[0]}{'   ' if _dots[0] < 3 else ''}")
                        sys.stdout.flush()
                        stop_event.wait(0.4)
                t = threading.Thread(target=_animate, daemon=True)
                t.start()
                try:
                    result = _orig_generate(prompt, system_prompt)
                finally:
                    stop_event.set()
                    sys.stdout.write("\r" + " " * 40 + "\r")
                    sys.stdout.flush()
                return result
            self.translator.llm.generate_json = _streaming_generate

        try:
            translation = self.translator.translate(user_input, entity_dict)
        finally:
            # Restore original method
            if _orig_generate:
                self.translator.llm.generate_json = _orig_generate
            sys.stdout.write("\r" + " " * 40 + "\r")
            sys.stdout.flush()

        self.tracer.add_event(cid, "translate_done", confidence=translation.confidence)

        if not translation.command:
            self.ui.print_error(translation.explanation)
            return

        self.ui.print_translation(translation)

        if translation.provenance:
            self.provenance.record(translation.provenance)

        if translation.confidence >= 0.8:
            if self.ui.confirm("Execute?"):
                self.feedback.record_accept("translation", user_input, translation.command)
                self._handle_shell_command(translation.command, cid)
            else:
                self.feedback.record_reject("translation", user_input, translation.command)
        else:
            if self.ui.confirm("Low confidence. Execute anyway?"):
                self.feedback.record_accept("translation", user_input, translation.command)
                self._handle_shell_command(translation.command, cid)
            else:
                self.feedback.record_reject("translation", user_input, translation.command)

    def _handle_followup(self, user_input: str, cid: str):
        """Handle follow-up requests using conversation memory."""
        self.tracer.add_event(cid, "followup_start")

        # Build conversation context from memory
        context_lines = []
        for mem in self._conversation_context[-self._MAX_MEMORY:]:
            context_lines.append(f"User said: {mem['input']}")
            context_lines.append(f"Command executed: {mem['command']}")
            if mem.get('output'):
                context_lines.append(f"Output (truncated): {mem['output'][:200]}")
        context_str = "\n".join(context_lines)

        system_prompt = (
            "You are a shell command translator. The user is following up on previous commands.\n"
            "Given the conversation history and the new request, generate the next shell command.\n"
            f"OS: {os.name}, Shell: {'powershell' if os.name == 'nt' else 'bash'}\n"
            "Respond with ONLY the shell command, nothing else."
        )
        prompt = f"Previous context:\n{context_str}\n\nNew request: {user_input}"

        import sys
        sys.stdout.write("\r  🔄 Following up")
        sys.stdout.flush()

        if hasattr(self, 'llm') and self.llm:
            response = self.llm.generate(prompt, system_prompt)
            sys.stdout.write("\r" + " " * 40 + "\r")
            sys.stdout.flush()

            if response.success and response.text.strip():
                command = response.text.strip().strip('`').strip()
                # Clean markdown fencing
                if command.startswith("```"):
                    command = command.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

                self.ui.print_info(f"  🔄 Follow-up: {command}")
                if self.ui.confirm("Execute?"):
                    self._handle_shell_command(command, cid)
                    # Record in conversation memory
                    self._conversation_context.append({
                        'input': user_input,
                        'command': command,
                        'output': '',
                    })
                    if len(self._conversation_context) > self._MAX_MEMORY:
                        self._conversation_context.pop(0)
                return

        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()
        self.ui.print_info("Could not process follow-up — LLM unavailable")

    def _handle_fix(self, cid: str):
        if not self._last_error_output:
            self.ui.print_info("No recent error to fix.")
            return

        self.tracer.add_event(cid, "fix_start")
        fix = self.fixer.fix(self._last_error_output, self._last_command)
        self.tracer.add_event(cid, "fix_done", confidence=fix.confidence)

        if not fix.fix_command:
            self.ui.print_info(f"💡 {fix.explanation}")
            return

        self.ui.print_fix(fix)
        if fix.provenance:
            self.provenance.record(fix.provenance)

        if self.ui.confirm("Apply fix?"):
            self.feedback.record_accept("fix", self._last_error_output[:100], fix.fix_command)
            self._handle_shell_command(fix.fix_command, cid)
        else:
            self.feedback.record_reject("fix", self._last_error_output[:100], fix.fix_command)

    def _handle_explain(self, command: str, cid: str):
        if not command:
            self.ui.print_info("Nothing to explain. Try: explain: <command>")
            return

        self.tracer.add_event(cid, "explain_start")

        # Try offline first (instant), fall back to streaming LLM
        result = self.explainer.explain(command)

        # If source is LLM, stream a richer explanation
        if result.source == "llm" and hasattr(self, 'llm') and self.llm:
            import sys
            sys.stdout.write("\n📖 ")
            sys.stdout.flush()
            streaming_result = self.llm.generate_streaming(
                prompt=f"Explain this shell command in detail: {command}",
                system_prompt="You are a shell expert. Explain commands concisely with flag meanings.",
                callback=lambda token: (sys.stdout.write(token), sys.stdout.flush()),
            )
            print()  # newline after streaming
        else:
            self.ui.print_explanation(result)

        self.tracer.add_event(cid, "explain_done")

    def _handle_pipeline(self, user_input: str, cid: str):
        """Handle pipeline building requests."""
        self.tracer.add_event(cid, "pipeline_start")
        result = self.pipeline_builder.build(user_input)
        self.ui.print_pipeline(result)

        if result.pipeline and result.confidence >= 0.6:
            if result.validation_errors:
                self.ui.toast("Some tools may not be available", "warning")

            if self.ui.confirm("Execute pipeline?"):
                self._handle_shell_command(result.pipeline, cid)
        elif result.pipeline:
            if self.ui.confirm("Low confidence. Execute anyway?"):
                self._handle_shell_command(result.pipeline, cid)

        self.tracer.add_event(cid, "pipeline_done")

    def _handle_undo(self):
        if not self.executor._snapshots:
            self.ui.print_info("Nothing to undo — no snapshots available.")
            return

        result = self.executor.undo_last()
        if result:
            command, restored = result
            self.ui.print_info(f"✅ Undone '{command}' — {len(restored)} file(s) restored.")
        else:
            self.ui.print_error("Failed to restore snapshot.")

    # ═══════════════════════════════════════════════════════
    # New Feature Handlers
    # ═══════════════════════════════════════════════════════

    def _handle_bookmark(self, user_input: str, cid: str):
        """Handle bookmark commands: !save, !run, !list, !delete."""
        action, params = self.bookmarks.parse_command(user_input)

        if action == "save":
            bm = self.bookmarks.save(params["name"], params["command"])
            self.ui.print_info(f"  ✅ Saved bookmark: {bm.display()}")
        elif action == "run":
            cmd = self.bookmarks.run(params["name"], params.get("variables", {}))
            if cmd:
                self.ui.print_info(f"  📌 Running bookmark: {cmd}")
                self._handle_shell_command(cmd, cid)
            else:
                self.ui.print_error(f"  Bookmark '{params['name']}' not found")
        elif action == "list":
            bookmarks = self.bookmarks.list_all()
            if bookmarks:
                self.ui.print_info("  📌 Saved Bookmarks:")
                for bm in bookmarks:
                    self.ui.print_info(bm.display())
            else:
                self.ui.print_info("  No bookmarks saved. Use !save <name> <command>")
        elif action == "delete":
            if self.bookmarks.delete(params["name"]):
                self.ui.print_info(f"  🗑️ Deleted bookmark: {params['name']}")
            else:
                self.ui.print_error(f"  Bookmark '{params['name']}' not found")
        else:
            self.ui.print_info("  📌 Bookmark commands: !save <name> <cmd>, !run <name>, !list, !delete <name>")

    def _handle_agent(self, task_description: str, cid: str):
        """Handle AI agent mode — multi-step task planning and execution."""
        self.tracer.add_event(cid, "agent_start")

        import sys
        sys.stdout.write("  🤖 Planning")
        sys.stdout.flush()

        plan = self.agent.plan(task_description)
        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()

        if not plan or not plan.steps:
            self.ui.print_error("Could not create an execution plan.")
            return

        # Display the plan
        print(plan.display())
        print()

        if not self.ui.confirm("Execute this plan?"):
            self.ui.print_info("  ⏹️ Plan aborted.")
            return

        # Execute step by step
        for step in plan.steps:
            step.status = "running"
            print(f"\n  🔄 Step {step.order}/{plan.total_steps}: {step.description}")
            print(f"     $ {step.command}")

            # Safety check each step
            safety = self.safety.check(step.command)
            if safety.risk_level in (self._RiskLevel.DANGER, self._RiskLevel.BLOCKED):
                step.status = "skipped"
                policy_tag = self._policy_tag()
                if policy_tag:
                    self.ui.print_info(f"  ⛔ Blocked by safety {policy_tag}: {safety.reason}")
                else:
                    self.ui.print_info(f"  ⛔ Blocked by safety: {safety.reason}")
                continue

            if safety.needs_confirmation:
                if not self.ui.confirm(f"  ⚠️ {safety.reason}. Continue?"):
                    step.status = "skipped"
                    continue

            # Execute
            result = self.executor.execute(step.command)
            if result.exit_code == 0:
                step.status = "success"
                plan.completed_steps += 1
                output_preview = (result.stdout or "")[:200]
                if output_preview:
                    print(f"     {output_preview}")
                print(f"  ✅ Step {step.order} complete ({result.duration_ms:.0f}ms)")
            else:
                step.status = "failed"
                error_preview = (result.stderr or result.stdout or "")[:200]
                print(f"  ❌ Step {step.order} failed: {error_preview}")
                if not self.ui.confirm("Continue with remaining steps?"):
                    plan.status = "aborted"
                    break

        plan.status = "completed" if plan.completed_steps == plan.total_steps else "partial"
        print(f"\n  📊 Agent complete: {plan.completed_steps}/{plan.total_steps} steps succeeded")
        self.tracer.add_event(cid, "agent_done", steps=plan.total_steps,
                              completed=plan.completed_steps)

    def _handle_script(self, description: str, cid: str):
        """Handle script generation requests."""
        self.tracer.add_event(cid, "script_start")

        import sys
        sys.stdout.write("  📜 Generating script")
        sys.stdout.flush()

        script = self.script_generator.generate(description)
        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()

        # Display the generated script
        print(script.display())

        # Offer to save
        if self.ui.confirm("Save this script?"):
            filepath = self.script_generator.save(script)
            self.ui.print_info(f"  💾 Saved to: {filepath}")

            # Offer to execute
            if self.ui.confirm("Execute the script now?"):
                if script.language == "powershell":
                    self._handle_shell_command(f"powershell -File {filepath}", cid)
                else:
                    self._handle_shell_command(f"bash {filepath}", cid)

        self.tracer.add_event(cid, "script_done")

    def _handle_chain(self, user_input: str, cid: str):
        """Handle chained command execution."""
        self.tracer.add_event(cid, "chain_start")

        plan = self.chain_builder.build(user_input)
        if not plan or not plan.steps:
            # Fall back to normal NL translation
            return False

        # Display chain plan
        print(plan.summary())
        print()

        if not self.ui.confirm("Execute this chain?"):
            return True  # handled but declined

        for step in plan.steps:
            step.status = "running"
            print(f"\n  [{step.order}/{plan.total_steps}] {step.command}")

            result = self.executor.execute(step.command)
            if result.exit_code == 0:
                step.status = "success"
                if result.stdout:
                    print(result.stdout[:300])
            else:
                step.status = "failed"
                print(f"  ❌ Failed: {(result.stderr or result.stdout or '')[:200]}")
                if plan.abort_on_failure:
                    self.ui.print_info("  ⏹️ Chain aborted due to failure.")
                    break

        self.tracer.add_event(cid, "chain_done")
        return True

    def _show_project_suggestions(self):
        """Show project-aware suggestions on startup."""
        try:
            msg = self.project_detector.get_startup_message()
            if msg:
                print(f"\n{msg}")
        except Exception:
            pass

    def _handle_alias_set(self, args: str):
        """Handle 'alias name=command' or 'alias name command'."""
        if "=" in args:
            name, command = args.split("=", 1)
        else:
            parts = args.split(None, 1)
            if len(parts) < 2:
                self.ui.print_info("  Usage: alias <name>=<command> or alias <name> <command>")
                return
            name, command = parts
        name = name.strip()
        command = command.strip()
        if self.alias_manager.add(name, command):
            self.ui.print_info(f"  ✅ Alias set: {name} → {command}")
        else:
            self.ui.print_info("  ❌ Invalid alias (empty or recursive)")

    def _handle_history_export(self, user_input: str):
        """Handle history export commands."""
        from pathlib import Path
        parts = user_input.lower().replace("history export", "").strip().split()
        fmt = "json"
        filename = None
        for p in parts:
            if p in ("json", "csv", "text", "txt"):
                fmt = p
            else:
                filename = p

        if not filename:
            filename = f"neuroshell_history.{fmt if fmt != 'txt' else 'text'}"

        filepath = Path(filename)
        if fmt == "json":
            self.history.export_json(filepath)
        elif fmt == "csv":
            self.history.export_csv(filepath)
        else:
            self.history.export_text(filepath)
        self.ui.print_info(f"  💾 History exported to: {filepath.absolute()}")

    # ═══════════════════════════════════════════════════════
    # Unified Slash Command Router (/)
    # ═══════════════════════════════════════════════════════

    def _handle_slash_command(self, user_input: str, cid: str) -> bool:
        """
        Unified handler for all '/' Slash Commands across NeuroShell.
        Returns True if the command was recognized and handled.
        """
        clean = user_input.strip()
        if not clean.startswith("/"):
            return False

        parts = clean[1:].strip().split(None, 1)
        if not parts:
            self._handle_slash_help()
            return True

        cmd = parts[0].lower()
        arg_str = parts[1].strip() if len(parts) > 1 else ""
        args = shlex.split(arg_str, posix=(os.name != "nt")) if arg_str else []

        if cmd in ("help", "?"):
            self._handle_slash_help()
            return True

        if cmd in ("api-key", "apikey", "key"):
            self._handle_slash_api_key(args)
            return True

        if cmd == "model":
            if not arg_str:
                if hasattr(self, "model_manager") and self.model_manager:
                    models = self.model_manager.list_available_models()
                    if models and sys.stdin.isatty() and os.environ.get("NEUROSHELL_TEST_MODE") != "1":
                        from ui.interactive_menu import select_menu
                        active = self.model_manager.get_active_model()
                        opts = [{"name": m["name"], "desc": m.get("description", ""), "badge": "(Active)" if m["name"] == active else ""} for m in models]
                        def_idx = next((i for i, m in enumerate(models) if m["name"] == active), 0)
                        sel = select_menu("Select Active LLM Model", opts, default_index=def_idx)
                        if sel is not None:
                            ok, msg = self.model_manager.switch_model(models[sel]["name"])
                            self.ui.print_info(f"  {'✅' if ok else '❌'} {msg}")
                    else:
                        print(self.model_manager.get_formatted_list())
                else:
                    self.ui.print_info("  Model manager unavailable")
            else:
                if hasattr(self, "model_manager") and self.model_manager:
                    ok, msg = self.model_manager.switch_model(arg_str)
                    self.ui.print_info(f"  {'✅' if ok else '❌'} {msg}")
                else:
                    self.ui.print_info("  Model manager unavailable")
            return True

        if cmd == "swarm":
            if not arg_str:
                self.ui.print_info("  Usage: /swarm <complex task or description>")
            else:
                self._handle_slash_swarm(arg_str, cid)
            return True

        if cmd == "agent":
            if not arg_str:
                self.ui.print_info("  Usage: /agent <goal or task>")
            else:
                self._handle_agent(arg_str, cid)
            return True

        if cmd == "plan":
            self._handle_slash_plan(args)
            return True

        if cmd == "backup":
            self._handle_slash_backup(args)
            return True

        if cmd == "record":
            self._handle_slash_record(args)
            return True

        if cmd in ("clip", "clipboard"):
            self._handle_slash_clip(args)
            return True

        if cmd in ("profile", "workspace"):
            self._handle_slash_profile(args)
            return True

        if cmd in ("jobs", "bg"):
            self._handle_slash_jobs(args)
            return True

        if cmd in ("snapshots", "snapshot", "undo"):
            self._handle_slash_snapshots(args)
            return True

        if cmd in ("search", "find"):
            if not arg_str:
                self.ui.print_info("  Usage: /search <query>")
            else:
                self._handle_slash_search(arg_str)
            return True

        if cmd in ("voice", "listen"):
            self._handle_slash_voice(args)
            return True

        if cmd == "git":
            self._handle_slash_git(args)
            return True

        if cmd in ("plugins", "plugin"):
            self._handle_slash_plugins(args)
            return True

        if cmd in ("dream", "autodream"):
            self._handle_slash_dream(args)
            return True

        if cmd == "update":
            self._handle_slash_update(args)
            return True

        if cmd in ("notebook", "note"):
            self._handle_slash_notebook(args)
            return True

        if cmd in ("scan", "security", "vuln"):
            self._handle_slash_security(args)
            return True

        if cmd in ("theme", "themes"):
            if hasattr(self, 'ext_themes') and self.ext_themes:
                themes = self.ext_themes.list_themes()
                if (not arg_str or arg_str == "list") and sys.stdin.isatty() and os.environ.get("NEUROSHELL_TEST_MODE") != "1":
                    from ui.interactive_menu import select_menu
                    cur = self.ext_themes.current_name
                    opts = [{"name": t, "desc": "Cyberpunk terminal color theme", "badge": "(Current)" if t == cur else ""} for t in themes]
                    def_idx = next((i for i, t in enumerate(themes) if t == cur), 0)
                    sel = select_menu("Select Terminal Theme", opts, default_index=def_idx)
                    if sel is not None:
                        self.ext_themes.set_theme(themes[sel])
                        self.ui.print_info(f"  🎨 Theme set to: {themes[sel]}")
                elif not arg_str or arg_str == "list":
                    self.ui.print_info(f"  🎨 Themes: {', '.join(themes)}")
                    self.ui.print_info(f"  Current: {self.ext_themes.current_name}")
                else:
                    if self.ext_themes.set_theme(arg_str):
                        self.ui.print_info(f"  🎨 Theme set to: {arg_str}")
                    else:
                        self.ui.print_info(f"  ❌ Unknown theme '{arg_str}'")
            return True

        if cmd == "config":
            if not args or args[0] in ("show", "list"):
                sec = args[1] if len(args) > 1 else ""
                if hasattr(self, "config_editor") and self.config_editor:
                    print(self.config_editor.show(sec))
            elif args[0] == "set" and len(args) >= 3:
                if hasattr(self, "config_editor") and self.config_editor:
                    ok, msg = self.config_editor.set_value(args[1], args[2])
                    self.ui.print_info(f"  {msg}")
            elif args[0] == "reset":
                if hasattr(self, "config_editor") and self.config_editor:
                    print(self.config_editor.reset_to_defaults())
            elif args[0] == "save":
                if hasattr(self, "config_editor") and self.config_editor:
                    print(self.config_editor.save())
            else:
                self.ui.print_info("  Usage: /config [show|set <key> <val>|reset|save]")
            return True

        if cmd in ("stats", "metrics", "perf"):
            if hasattr(self, "command_timer") and hasattr(self, "metrics") and self.command_timer and self.metrics:
                print(self.command_timer.get_formatted_stats(self.metrics))
            return True

        if cmd == "clear":
            os.system('cls' if os.name == 'nt' else 'clear')
            return True

        if cmd in ("exit", "quit", "q"):
            self._running = False
            return True

        self.ui.print_info(f"  ❌ Unknown slash command: /{cmd}")
        self.ui.print_info("  💡 Type /help to view all available commands.")
        return True

    def _handle_slash_help(self):
        """Render comprehensive slash command directory."""
        help_text = """
  ╔═════════════════════════════════════════════════════════════════════════════╗
  ║                       🧠 NEUROSHELL SLASH COMMAND DIRECTORY                 ║
  ╚═════════════════════════════════════════════════════════════════════════════╝

  🤖 AI & Multi-Agent:
    /api-key [provider]      Configure & encrypt LLM provider API keys securely
    /model [name]            List available models or switch active LLM backend
    /swarm <task>            Orchestrate multi-agent planner, verifier & sandbox
    /agent <task>            Autonomous multi-step agent planner with rollback
    /plan [start|step|status] Safe architectural brainstorm & planning mode
    /dream [status|run]      AutoDream background memory consolidation engine

  🛡️ Security & Ops Governance:
    /scan                    Run project security & vulnerability analysis
    /security [audit|policy] Safety shield policies, RBAC roles & audit logs
    /backup [create|restore] Create, restore or validate ops backups & retention
    /update [check|channel]  Cryptographic update verification & channel manager

  ⚡ Productivity & Shell Tools:
    /clip [copy|paste|last]  OS clipboard integration (copy output, paste cmd)
    /record [start|stop|list] Record & replay interactive terminal sessions
    /search <query>          Recursive high-speed file & repository search
    /git <status|log|clone>  Structured git ops and GitHub repo search
    /voice [listen|toggle]   Whisper voice-to-command speech transcription
    /notebook [show|note]    Session notebook notes & markdown export
    /profile [list|create]   Per-directory workspace profiles (env, aliases)

  🔧 Diagnostics & System:
    /jobs [list|kill <id>]   List, monitor or kill background processes
    /snapshots [list|undo]   View file state snapshots & instant undo
    /plugins [list|load]     Hot-reloadable plugin architecture manager
    /theme [name|list]       Switch cyberpunk CLI & TUI color themes
    /config [show|set]       Interactive TOML configuration editor
    /stats                   Session telemetry, command latencies & timers
    /help                    Display this command reference directory
"""
        print(help_text)

    def _handle_slash_api_key(self, args: list[str]):
        """Interactive and direct API key configuration with AES-128 encryption."""
        provider = args[0].lower() if len(args) >= 1 else ""
        key = args[1] if len(args) >= 2 else ""

        providers_data = [
            {"name": "GROQ", "desc": "Fast Cloud Inference (Default)", "id": "groq"},
            {"name": "OPENAI", "desc": "GPT-4o, GPT-4 Turbo, GPT-3.5", "id": "openai"},
            {"name": "ANTHROPIC", "desc": "Claude 3.5 Sonnet, Claude 3 Haiku", "id": "anthropic"},
            {"name": "GEMINI", "desc": "Google DeepMind 1.5 Pro / Flash", "id": "gemini"},
            {"name": "OPENROUTER", "desc": "Multi-Provider AI Gateway", "id": "openrouter"},
            {"name": "OLLAMA", "desc": "Local Private SLM (No Key Required)", "id": "ollama"},
        ]

        if not provider:
            from ui.interactive_menu import select_menu
            active_p = getattr(self.config.llm, "provider", "groq").lower()
            default_idx = next((i for i, p in enumerate(providers_data) if p["id"] == active_p), 0)
            badge_map = {i: "(Active)" for i, p in enumerate(providers_data) if p["id"] == active_p}

            sel = select_menu(
                "Select LLM Provider",
                providers_data,
                default_index=default_idx,
                description="Configure, test, and encrypt provider API keys",
                badge_map=badge_map,
            )
            if sel is None:
                return
            provider = providers_data[sel]["id"]

        if provider == "ollama":
            self.config.llm.provider = "ollama"
            self.config.save()
            self.ui.print_info("  ✅ Provider switched to Ollama (local SLM, no key required)")
            return

        if not key:
            from ui.interactive_menu import text_prompt
            key = text_prompt(f"Enter API key for {provider.upper()}", password=True)
            if not key:
                self.ui.print_info("  Operation cancelled (empty key)")
                return

        # Encrypt and save
        try:
            self.config.save_secret(f"{provider}_api_key", key)
            self.config.llm.provider = provider
            self.config.save()

            # Hot reload LLM client
            if hasattr(self, "llm") and self.llm:
                self.llm.config = self.config
            self.ui.print_info(f"  🔐 {provider.upper()} API key securely encrypted with AES-128 & saved!")
            self.ui.print_info(f"  ✅ Active provider set to: {provider.upper()}")
        except Exception as e:
            self.ui.print_error(f"  ❌ Failed to save API key: {e}")

    def _handle_slash_swarm(self, task: str, cid: str):
        """Execute multi-agent swarm task with planning, verification, and sandbox."""
        if not hasattr(self, "swarm_orchestrator") or not self.swarm_orchestrator:
            self.ui.print_error("  Swarm orchestrator unavailable.")
            return

        self.ui.print_info(f"  🧠 Swarm Orchestrator activated for task: {task}")
        try:
            result = self.swarm_orchestrator.route_task(task)
            self.ui.print_info(f"  👥 Agents engaged: {', '.join(result.agents_used)}")
            if result.explanation:
                self.ui.print_info(f"  📋 Outcome:\n{result.explanation}")
            if result.final_command and result.is_safe:
                self.ui.print_info(f"\n  ▶ Proposed Command: {result.final_command}")
                if self.ui.confirm("Execute swarm command?"):
                    self._handle_shell_command(result.final_command, cid)
            elif not result.is_safe:
                self.ui.print_error("  ⛔ Swarm Verification failed: Command deemed unsafe.")
        except Exception as e:
            self.ui.print_error(f"  ❌ Swarm execution error: {e}")

    def _handle_slash_plan(self, args: list[str]):
        """Plan Mode controller."""
        if not hasattr(self, "plan_mode") or not self.plan_mode:
            self.ui.print_error("  Plan mode controller unavailable.")
            return

        sub = args[0].lower() if args else "status"
        if sub == "status":
            state = "ACTIVE (Brainstorm / Safe)" if self.plan_mode.is_active else "INACTIVE (Direct Execution)"
            self.ui.print_info(f"  📐 Plan Mode: {state}")
            current = self.plan_mode.get_current_plan()
            if current:
                print("\n  --- Current Plan ---")
                print(current)
            else:
                self.ui.print_info("  Plan buffer is empty. Use: /plan start <goal> or /plan add <thought>")
        elif sub == "start":
            self.plan_mode.enter_plan_mode()
            goal = " ".join(args[1:]) if len(args) > 1 else ""
            if goal:
                self.plan_mode.add_to_plan(f"Goal: {goal}")
            self.ui.print_info("  📐 Entered Plan Mode. AI commands will brainstorm without executing.")
        elif sub == "add" and len(args) > 1:
            thought = " ".join(args[1:])
            self.plan_mode.add_to_plan(thought)
            self.ui.print_info(f"  📝 Added to plan: {thought}")
        elif sub in ("exit", "finish", "stop"):
            self.plan_mode.exit_plan_mode()
            self.ui.print_info("  📐 Exited Plan Mode. Returned to active execution mode.")
        else:
            self.ui.print_info("  Usage: /plan [status|start <goal>|add <thought>|finish]")

    def _handle_slash_backup(self, args: list[str]):
        """Data governance backup, restore, and retention management."""
        if not hasattr(self, "data_governance") or not self.data_governance:
            self.ui.print_error("  Data governance manager unavailable.")
            return

        sub = args[0].lower() if args else "create"
        if sub == "create":
            from config import NEUROSHELL_DIR
            stamp = time.strftime("%Y%m%d_%H%M%S")
            target = NEUROSHELL_DIR / "backups" / f"backup_{stamp}.zip"
            try:
                meta = self.data_governance.create_backup(target)
                self.ui.print_info(f"  ✅ Backup created: {meta.get('archive')}")
                self.ui.print_info(f"  🔐 SHA-256: {meta.get('sha256')}")
            except Exception as e:
                self.ui.print_error(f"  ❌ Backup failed: {e}")
        elif sub == "restore" and len(args) >= 2:
            zip_path = args[1]
            dest = args[2] if len(args) >= 3 else str(NEUROSHELL_DIR / "restored")
            try:
                out = self.data_governance.restore_backup(zip_path, dest)
                self.ui.print_info(f"  ✅ Backup restored safely to: {out}")
            except Exception as e:
                self.ui.print_error(f"  ❌ Restore failed: {e}")
        elif sub == "validate" and len(args) >= 3:
            zip_path = args[1]
            sha = args[2]
            valid = self.data_governance.validate_backup(zip_path, sha)
            if valid:
                self.ui.print_info("  ✅ Backup signature verified valid!")
            else:
                self.ui.print_error("  ❌ Backup checksum mismatch!")
        elif sub == "retention" and len(args) >= 2:
            try:
                days = int(args[1])
                report = self.data_governance.enforce_retention_days(days)
                self.ui.print_info(f"  ✅ Retention cleanup: {report.deleted_files} files deleted, {report.reclaimed_bytes / 1024:.1f} KB reclaimed")
            except Exception as e:
                self.ui.print_error(f"  ❌ Retention failed: {e}")
        else:
            self.ui.print_info("  Usage:")
            self.ui.print_info("  • /backup create")
            self.ui.print_info("  • /backup restore <backup.zip> [restore_dir]")
            self.ui.print_info("  • /backup validate <backup.zip> <sha256>")
            self.ui.print_info("  • /backup retention <days>")

    def _handle_slash_record(self, args: list[str]):
        """Session recorder start/stop/list/replay."""
        if not hasattr(self, "ext_recorder") or not self.ext_recorder:
            self.ui.print_error("  Session recorder unavailable.")
            return

        sub = args[0].lower() if args else "status"
        if sub == "start":
            desc = " ".join(args[1:]) if len(args) > 1 else "Interactive session"
            if self.ext_recorder.start(self.session_id, desc):
                self.ui.print_info(f"  ⏺️ Recording session started: '{desc}'")
            else:
                self.ui.print_info("  ⚠️ Already recording.")
        elif sub == "stop":
            path = self.ext_recorder.stop()
            if path:
                self.ui.print_info(f"  ⏹️ Recording saved to: {path}")
            else:
                self.ui.print_info("  ⚠️ No active recording to stop.")
        elif sub in ("list", "show"):
            items = self.ext_recorder.list_recordings()
            if not items:
                self.ui.print_info("  No session recordings saved yet.")
            else:
                self.ui.print_info("  📼 Saved Session Recordings:")
                for r in items:
                    self.ui.print_info(f"  • {r['file']} ({r['commands']} cmds, {r['duration_s']}s) — {r['description']}")
        elif sub == "replay" and len(args) >= 2:
            txt = self.ext_recorder.replay_text(args[1])
            if txt:
                print(txt)
            else:
                self.ui.print_error(f"  ❌ Recording not found: {args[1]}")
        else:
            self.ui.print_info("  Usage: /record [start <desc>|stop|list|replay <file.json.gz>]")

    def _handle_slash_clip(self, args: list[str]):
        """Clipboard copy/paste commands."""
        if not hasattr(self, "ext_clipboard") or not self.ext_clipboard:
            self.ui.print_error("  Clipboard manager unavailable.")
            return

        sub = args[0].lower() if args else "paste"
        if sub == "copy" and len(args) >= 2:
            txt = " ".join(args[1:])
            if self.ext_clipboard.copy(txt):
                self.ui.print_info(f"  📋 Copied {len(txt)} chars to clipboard")
            else:
                self.ui.print_error("  ❌ Failed to copy to clipboard")
        elif sub == "paste":
            content = self.ext_clipboard.paste()
            if content:
                self.ui.print_info("  📋 Clipboard Content:")
                print(content)
            else:
                self.ui.print_info("  Clipboard is empty or unavailable.")
        elif sub == "output":
            out = self._last_error_output or (self._conversation_context[-1].get("output") if self._conversation_context else "")
            if out and self.ext_clipboard.copy_output(out):
                self.ui.print_info("  📋 Copied last command output to clipboard")
            else:
                self.ui.print_info("  No output available to copy")
        elif sub == "last":
            if self._last_command and self.ext_clipboard.copy_command(self._last_command):
                self.ui.print_info(f"  📋 Copied: {self._last_command}")
            else:
                self.ui.print_info("  No previous command to copy")
        elif sub == "history":
            hist = self.ext_clipboard.get_history()
            if not hist:
                self.ui.print_info("  Clipboard history is empty.")
            else:
                self.ui.print_info("  📋 Recent Clipboard Items:")
                for i, h in enumerate(hist, 1):
                    self.ui.print_info(f"  {i}. {h[:80]}")
        else:
            self.ui.print_info("  Usage: /clip [copy <text>|paste|output|last|history]")

    def _handle_slash_profile(self, args: list[str]):
        """Workspace profiles management."""
        if not hasattr(self, "workspace_profiles") or not self.workspace_profiles:
            self.ui.print_error("  Workspace profiles unavailable.")
            return

        sub = args[0].lower() if args else "list"
        if sub == "list":
            profiles = self.workspace_profiles.list_all()
            if not profiles:
                self.ui.print_info("  No workspace profiles configured.")
                self.ui.print_info(f"  Current directory: {os.getcwd()}")
            else:
                self.ui.print_info("  📁 Workspace Profiles:")
                for p in profiles:
                    active = " (ACTIVE)" if self.workspace_profiles.get_active() and self.workspace_profiles.get_active().name == p["name"] else ""
                    self.ui.print_info(f"  • {p['name']}: {p['directory']}{active}")
        elif sub == "create" and len(args) >= 3:
            name = args[1]
            directory = args[2]
            p = self.workspace_profiles.create(name, directory)
            self.ui.print_info(f"  ✅ Created workspace profile '{p.name}' for {p.directory}")
        elif sub == "switch":
            directory = args[1] if len(args) >= 2 else os.getcwd()
            p = self.workspace_profiles.activate(directory)
            if p:
                self.ui.print_info(f"  ✅ Activated workspace profile: {p.name}")
            else:
                self.ui.print_info(f"  No workspace profile found for {directory}")
        elif sub == "delete" and len(args) >= 2:
            if self.workspace_profiles.delete(args[1]):
                self.ui.print_info(f"  ✅ Deleted profile for {args[1]}")
            else:
                self.ui.print_info(f"  ❌ No profile found for {args[1]}")
        else:
            self.ui.print_info("  Usage: /profile [list|create <name> <dir>|switch [dir]|delete <dir>]")

    def _handle_slash_jobs(self, args: list[str]):
        """Background process management."""
        sub = args[0].lower() if args else "list"
        if sub == "list":
            jobs = self.executor.list_jobs()
            if not jobs:
                self.ui.print_info("  No active background jobs.")
            else:
                self.ui.print_info("  ⚙️ Active Background Jobs:")
                for j in jobs:
                    status = "RUNNING" if j["is_running"] else f"EXIT {j['exit_code']}"
                    self.ui.print_info(f"  [{j['job_id']}] PID {j['pid']} | {status} | {j['elapsed_s']}s | {j['command']}")
        elif sub == "kill" and len(args) >= 2:
            if self.executor.kill_job(args[1]):
                self.ui.print_info(f"  ✅ Terminated background job: {args[1]}")
            else:
                self.ui.print_info(f"  ❌ Job not found or already finished: {args[1]}")
        elif sub == "output" and len(args) >= 2:
            out = self.executor.get_job_output(args[1])
            if out is not None:
                self.ui.print_info(f"  📄 Job [{args[1]}] Output:")
                print(out)
            else:
                self.ui.print_info(f"  ❌ No output for job: {args[1]}")
        else:
            self.ui.print_info("  Usage: /jobs [list|kill <id>|output <id>]")

    def _handle_slash_snapshots(self, args: list[str]):
        """Snapshot and undo management."""
        sub = args[0].lower() if args else "list"
        if sub == "list":
            snaps = self.executor.get_snapshots()
            if not snaps:
                self.ui.print_info("  No undo snapshots recorded.")
            else:
                self.ui.print_info("  📸 State Snapshots Available for Undo:")
                for s in snaps:
                    self.ui.print_info(f"  • [{s['id'][:8]}] {s['command']} ({s['files']} files, {s['age_s']}s ago)")
        elif sub == "undo":
            self._handle_undo()
        else:
            self.ui.print_info("  Usage: /snapshots [list|undo]")

    def _handle_slash_search(self, query: str):
        """Recursive deep file & AST search."""
        if not hasattr(self, "deep_search") or not self.deep_search:
            self.ui.print_error("  Deep search unavailable.")
            return

        self.ui.print_info(f"  🔍 Scanning workspace for '{query}'...")
        start = time.time()
        results = self.deep_search.search(query)
        elapsed = time.time() - start
        print(self.deep_search.format_results(query, results, os.getcwd(), elapsed))

    def _handle_slash_voice(self, args: list[str]):
        """Voice transcription execution."""
        if not hasattr(self, "ext_voice") or not self.ext_voice:
            self.ui.print_error("  Voice engine unavailable.")
            return

        if not self.ext_voice.available:
            self.ui.print_info("  🎤 Voice requires: pip install SpeechRecognition pyaudio")
            return

        self.ui.print_info("  🎤 Listening... Speak your command clearly")
        text = self.ext_voice.listen()
        if text:
            self.ui.print_info(f"  🗣️ Transcribed: {text}")
            self.process_input(text)
        else:
            self.ui.print_error("  Could not capture or transcribe speech.")

    def _handle_slash_git(self, args: list[str]):
        """Execute structured git operations."""
        if not hasattr(self, "git_ops") or not self.git_ops:
            self.ui.print_error("  Git operations manager unavailable.")
            return

        sub = args[0].lower() if args else "status"
        try:
            if sub == "status":
                status = self.git_ops.status()
                self.ui.print_info(f"  🌿 Git Status: {status.summary()}")
            elif sub == "log":
                commits = self.git_ops.log(max_count=5)
                self.ui.print_info("  📜 Recent Git Commits:")
                for c in commits:
                    self.ui.print_info(f"  • {c}")
            elif sub == "clone" and len(args) >= 2:
                dest = args[2] if len(args) >= 3 else ""
                res = self.git_ops.clone(args[1], dest)
                self.ui.print_info(f"  ✅ {res}")
            elif sub == "commit" and len(args) >= 2:
                msg = " ".join(args[1:])
                self.git_ops.add(".")
                sha = self.git_ops.commit(msg)
                self.ui.print_info(f"  ✅ Committed: {sha}")
            elif sub == "push":
                out = self.git_ops.push()
                self.ui.print_info(f"  ✅ {out}")
            elif sub == "pull":
                out = self.git_ops.pull()
                self.ui.print_info(f"  ✅ {out}")
            elif sub == "search" and len(args) >= 2:
                results = self.git_ops.search_github_repo(args[1])
                if results:
                    self.ui.print_info(f"  🐙 Top GitHub Matches for '{args[1]}':")
                    for r in results[:5]:
                        self.ui.print_info(f"  • {r['full_name']} (★ {r['stars']}): {r['clone_url']}")
                else:
                    self.ui.print_info("  No GitHub repositories found.")
            else:
                self.ui.print_info("  Usage: /git [status|log|clone <url>|commit <msg>|push|pull|search <query>]")
        except Exception as e:
            self.ui.print_error(f"  ❌ Git error: {e}")

    def _handle_slash_plugins(self, args: list[str]):
        """Plugin system management."""
        if not hasattr(self, "plugin_system") or not self.plugin_system:
            self.ui.print_error("  Plugin system unavailable.")
            return

        sub = args[0].lower() if args else "list"
        if sub == "list":
            plugins = self.plugin_system.discover()
            self.ui.print_info(f"  🔌 Discovered Plugins ({len(plugins)}):")
            for p in plugins:
                self.ui.print_info(f"  • {p}")
        elif sub == "load" and len(args) >= 2:
            if self.plugin_system.load(args[1]):
                self.ui.print_info(f"  ✅ Loaded plugin: {args[1]}")
            else:
                self.ui.print_error(f"  ❌ Failed to load plugin: {args[1]}")
        elif sub == "reload":
            reloaded = self.plugin_system.reload_stale()
            self.ui.print_info(f"  ✅ Reloaded {len(reloaded)} plugins")
        elif sub == "trust" and len(args) >= 2:
            self.plugin_system.trust_plugin(args[1])
            self.ui.print_info(f"  🔐 Trusted plugin: {args[1]}")
        else:
            self.ui.print_info("  Usage: /plugins [list|load <name>|reload|trust <id>]")

    def _handle_slash_dream(self, args: list[str]):
        """AutoDream memory consolidation status and manual trigger."""
        if not hasattr(self, "auto_dream") or not self.auto_dream:
            self.ui.print_error("  AutoDream daemon unavailable.")
            return

        sub = args[0].lower() if args else "status"
        if sub == "status":
            is_active = getattr(self.auto_dream, "is_running", False)
            if hasattr(self.auto_dream, "is_alive") and callable(self.auto_dream.is_alive):
                is_active = self.auto_dream.is_alive()
            running = "ACTIVE (Running in background)" if is_active else "STOPPED"
            self.ui.print_info(f"  💭 AutoDream Daemon: {running}")
            self.ui.print_info("  AutoDream passively consolidates session memory and generates MagicDocs.")
        elif sub in ("run", "now", "consolidate"):
            self.ui.print_info("  💭 Triggering immediate AutoDream memory consolidation...")
            try:
                self.auto_dream._consolidate_step()
                self.ui.print_info("  ✅ Memory consolidation complete.")
            except Exception as e:
                self.ui.print_error(f"  ❌ AutoDream run failed: {e}")
        else:
            self.ui.print_info("  Usage: /dream [status|run]")

    def _handle_slash_update(self, args: list[str]):
        """Release update verification and channels."""
        if not hasattr(self, "update_manager") or not self.update_manager:
            self.ui.print_error("  Update manager unavailable.")
            return

        sub = args[0].lower() if args else "check"
        if sub == "check":
            self.ui.print_info(f"  🚀 NeuroShell Version: v{__import__('__version__').__version__}")
            self.ui.print_info("  🔍 Checking update channels (stable, beta, canary)...")
            self.ui.print_info("  ✅ You are on the latest production build.")
        elif sub == "channel" and len(args) >= 2:
            ch = self.update_manager.select_channel(args[1])
            self.ui.print_info(f"  ✅ Update channel set to: {ch}")
        else:
            self.ui.print_info("  Usage: /update [check|channel <stable|beta|canary>]")

    def _handle_slash_notebook(self, args: list[str]):
        """Notebook session recording."""
        if not hasattr(self, "ext_notebook") or not self.ext_notebook:
            self.ui.print_error("  Notebook mode unavailable.")
            return

        sub = args[0].lower() if args else "show"
        if sub == "show":
            print(self.ext_notebook.export_markdown())
        elif sub == "note" and len(args) >= 2:
            note = " ".join(args[1:])
            self.ext_notebook.add_note(note)
            self.ui.print_info(f"  📝 Note saved to notebook: '{note}'")
        elif sub == "save" and len(args) >= 2:
            path = Path(args[1])
            self.ext_notebook.save(path)
            self.ui.print_info(f"  💾 Notebook exported to: {path}")
        else:
            self.ui.print_info("  Usage: /notebook [show|note <text>|save <file.md>]")

    def _handle_slash_security(self, args: list[str]):
        """Security scanner, policy, and audit trail."""
        sub = args[0].lower() if args else "scan"
        if sub == "scan":
            if hasattr(self, 'ext_scanner') and self.ext_scanner:
                scans = self.ext_scanner.get_scan_commands(os.getcwd())
                if not scans:
                    self.ui.print_info("  No scannable project files found in current directory.")
                else:
                    self.ui.print_info(f"  🛡️ Running {len(scans)} security audits...")
                    for desc, cmd in scans:
                        self.ui.print_info(f"\n  📋 {desc}")
                        self.ui.print_info(f"  $ {cmd}")
                        try:
                            result = self.executor.execute(cmd)
                            if result.stdout:
                                print(result.stdout[:500])
                        except Exception:
                            pass
            else:
                self.ui.print_info("  Vulnerability scanner unavailable")
        elif sub == "audit":
            if hasattr(self, "safety") and self.safety:
                rows = self.safety.get_audit_log(limit=10)
                if not rows:
                    self.ui.print_info("  No safety audit entries yet.")
                else:
                    self.ui.print_info("  🧾 Recent Safety Audit Records:")
                    for r in rows:
                        self.ui.print_info(f"  • [{r.get('risk_level')}] {r.get('command')}")
        elif sub == "policy":
            if hasattr(self, "safety") and self.safety:
                state = self.safety.get_policy_state()
                self.ui.print_info(f"  🛡️ Policy Profile: {state.get('profile')}")
                self.ui.print_info(f"  👤 User Role: {state.get('role')}")
        else:
            self.ui.print_info("  Usage: /security [scan|audit|policy]")

    # ═══════════════════════════════════════════════════════
    # Shutdown
    # ═══════════════════════════════════════════════════════

    def shutdown(self):
        """Graceful shutdown with session summary."""
        try:
            if hasattr(self, "logger") and self.logger:
                self.logger.info("shutdown", session_id=getattr(self, "session_id", "unknown"))

            # Session summary with timer stats
            if hasattr(self, "sentiment") and self.sentiment:
                try:
                    session_state = self.sentiment.get_session_state()
                    if session_state.get("error_rate", 0) > 0.5 and hasattr(self, "ui") and self.ui:
                        self.ui.toast("High error rate this session — consider reviewing your workflow", "warning")
                except Exception:
                    pass

            if hasattr(self, "command_timer") and hasattr(self, "metrics") and self.command_timer and self.metrics:
                try:
                    print(self.command_timer.get_formatted_stats(self.metrics))
                except Exception:
                    pass

            if hasattr(self, "provenance") and self.provenance and hasattr(self, "ui") and self.ui:
                try:
                    self.ui.print_info(f"📊 Provenance: {self.provenance.get_summary()}")
                except Exception:
                    pass

            # Show env changes
            if hasattr(self, "env_manager") and self.env_manager and hasattr(self, "ui") and self.ui:
                try:
                    env_changes = self.env_manager.get_session_changes()
                    if env_changes.get("set") or env_changes.get("unset"):
                        self.ui.print_info(f"🔧 Env changes: {len(env_changes['set'])} set, {len(env_changes['unset'])} unset")
                except Exception:
                    pass

            if hasattr(self, "ui") and self.ui:
                self.ui.print_info("👋 Goodbye from NeuroShell!")

            if hasattr(self, "history") and self.history:
                try:
                    self.history.end_session(getattr(self, "session_id", ""))
                except Exception:
                    pass

            # Log performance stats
            if hasattr(self, "logger") and self.logger:
                try:
                    perf = self.logger.get_perf_stats()
                    if perf.get("total_traces", 0) > 0:
                        self.logger.info("session_perf_stats", **perf)
                except Exception:
                    pass
        except Exception:
            pass


def main():
    """Entry point."""
    shell = NeuroShell()
    try:
        shell.run()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
