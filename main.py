# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
#!/usr/bin/env python3
"""
NeuroShell v4 — AI-Powered Terminal
Main orchestrator: signal handling, lazy loading, status bar, pipeline routing.

Usage:
    python main.py
"""

import sys
import os
import time
import uuid
import signal
import atexit
import shlex
from pathlib import Path
from typing import Optional

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config, NEUROSHELL_DIR

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
        # ── Load config ──────────────────────────────
        self.config = load_config()

        # ── Observability (load first for logging) ───
        from observability.logger import StructuredLogger
        self.logger = StructuredLogger("main")

        # ── Core Layer ───────────────────────────────
        from core.executor import ShellExecutor
        from core.context import ContextManager
        from core.history import HistoryStore
        from core.output_parser import OutputParser
        from core.dependency_resolver import DependencyResolver

        self.executor = ShellExecutor(self.config)
        self.context = ContextManager(self.config)
        self.history = HistoryStore()
        self.parser = OutputParser()
        self.dep_resolver = DependencyResolver(self.context)

        # ── Observability ────────────────────────────
        from observability.tracer import EventTracer
        from observability.provenance import ProvenanceTracker

        self.tracer = EventTracer(self.logger)
        self.provenance = ProvenanceTracker()

        # ── Learning/Metrics (lazy load) ─────────────
        from learning.metrics import MetricsTracker
        self.metrics = MetricsTracker()

        # ── LLM ──────────────────────────────────────
        from llm.client import LLMClient
        self.llm = LLMClient(self.config)

        # ── NLP Fast Layer ───────────────────────────
        from nlp.intent_classifier import IntentClassifier
        from nlp.entity_extractor import EntityExtractor
        from nlp.sentiment import SentimentDetector

        self.intent_classifier = IntentClassifier()
        self.entity_extractor = EntityExtractor()
        self.sentiment = SentimentDetector()

        # ── Intelligence ─────────────────────────────
        from intelligence.translator import Translator
        from intelligence.safety import SafetyChecker, RiskLevel
        from intelligence.error_fixer import ErrorFixer
        from intelligence.explainer import Explainer
        from intelligence.autocomplete import Autocomplete
        from intelligence.pipeline_builder import PipelineBuilder
        from intelligence.fuzzy_corrector import FuzzyCorrector
        from intelligence.chain_builder import ChainBuilder
        from intelligence.project_detector import ProjectDetector
        from intelligence.bookmarks import BookmarkManager
        from intelligence.agent import AgentPlanner
        from intelligence.script_generator import ScriptGenerator
        from intelligence.phrase_dictionary import PhraseDictionary
        import intelligence.pii_scrubber as _pii_scrubber
        self.pii_scrubber = _pii_scrubber
        from intelligence.offline_fallback import OfflineFallbackManager


        self.translator = Translator(self.llm, self.context, self.history)
        self.safety = SafetyChecker(self.config, self.llm)
        self.fixer = ErrorFixer(self.llm, self.history, self.context)
        self.explainer = Explainer(self.llm, self.context)
        self.autocomplete = Autocomplete(self.history, self.context)
        self.pipeline_builder = PipelineBuilder(self.llm, self.context)
        self._RiskLevel = RiskLevel

        # ── New futuristic modules ────────────────────
        self.fuzzy_corrector = FuzzyCorrector()
        self.chain_builder = ChainBuilder(self.llm, self.translator)
        self.project_detector = ProjectDetector()
        self.bookmarks = BookmarkManager(self.history)
        self.agent = AgentPlanner(self.llm, self.executor, self.safety)
        self.script_generator = ScriptGenerator(self.llm)
        self.phrase_dict = PhraseDictionary()
        
        self.offline_fallback = OfflineFallbackManager(self.config)
        
        # Try importing C++ engine gracefully
        try:
            import cpp_engine.cpp_engine_core as cpp
            self.cpp_parser = cpp.FastParser()
            self.cpp_matcher = cpp.FuzzyMatcher()
            self._cpp_enabled = True
        except ImportError:
            self._cpp_enabled = False


        # ── New Feature Modules ──────────────────────
        from extensions.alias_manager import AliasManager
        from core.env_manager import EnvManager
        from llm.model_manager import ModelManager
        from extensions.config_editor import ConfigEditor
        from core.timer import CommandTimer
        from extensions.auto_docs import AutoDocsGenerator
        from intelligence.smart_suggestions import SmartSuggester
        from intelligence.smart_open import SmartOpenEngine

        self.alias_manager = AliasManager()
        self.env_manager = EnvManager()
        self.model_manager = ModelManager(self.config, self.llm)
        self.config_editor = ConfigEditor(self.config)
        self.command_timer = CommandTimer(self.executor)
        self.docs_generator = AutoDocsGenerator(self.history, self.pattern_learner if hasattr(self, 'pattern_learner') else None)
        self.smart_suggester = SmartSuggester(self.history, self.context)
        self.smart_open = SmartOpenEngine()  # singleton — handles open/clone/launch/power intents

        # ── Phase 7 Agentic Features ─────────────────
        from intelligence.coordinator import Coordinator
        from intelligence.mcp.mcp_client import MCPClient
        from intelligence.lsp.lsp_client import LSPClient
        from intelligence.tools.mcp_tool import MCPTool
        from intelligence.tools.lsp_tool import LSPTool
        from intelligence.tools.task_tools import TaskSystemTool
        from intelligence.tools.mode_tools import ModeTool
        from intelligence.tools.teammate_tool import TeammateTool
        from intelligence.modes.plan_mode import PlanModeController
        from intelligence.memory.session_memory import SessionMemory
        from intelligence.swarm import SwarmOrchestrator

        # Setup short-term rolling context
        self.session_memory = SessionMemory(max_turns=15)

        # MCP is optional — engine stays fully operational if no MCP server is running
        try:
            self.mcp_client = MCPClient("http://localhost:8000")
        except Exception:
            self.mcp_client = None

        # LSPClient takes only the server command list
        self.lsp_client = LSPClient(["python", "-m", "pylsp"])
        
        from intelligence.tasks.task_manager import TaskManager

        self.task_manager = TaskManager()

        self.coordinator = Coordinator(self.llm, self.context)
        if self.mcp_client is not None:
            self.coordinator.register_tool(MCPTool(self.mcp_client))
        self.coordinator.register_tool(LSPTool(self.lsp_client))
        self.coordinator.register_tool(TaskSystemTool(self.task_manager))
        self.coordinator.register_tool(TeammateTool())

        # PlanModeController takes no constructor args
        self.plan_mode = PlanModeController()

        # Mode tool requires the instantiated plan_mode
        self.coordinator.register_tool(ModeTool(self.plan_mode))

        # SwarmOrchestrator takes (llm_client, context_manager)
        self.swarm_orchestrator = SwarmOrchestrator(self.llm, self.context)

        # ── Intelligence Background Services ─────────
        from intelligence.services.magic_docs import MagicDocs
        from intelligence.memory.auto_dream import AutoDreamDaemon

        self.magic_docs = MagicDocs(self.llm)
        self.auto_dream = AutoDreamDaemon(
            self.session_memory, self.llm,
            magic_docs=self.magic_docs,
            ui_callback=lambda m: print(f"[AutoDream] {m}")
        )

        # Auto-start memory daemon
        self.auto_dream.start()
        
        # This will be updated by the UI when the toggle switches
        self.mode = "Builder"

        # ── Learning (lazy) ──────────────────────────
        from learning.pattern_learner import PatternLearner
        from learning.predictor import Predictor
        from learning.feedback_loop import FeedbackLoop

        self.pattern_learner = PatternLearner(self.history)
        self.predictor = Predictor(self.history)
        self.feedback = FeedbackLoop(self.history, self.intent_classifier)

        # Re-link docs generator with pattern_learner now that it exists
        self.docs_generator = AutoDocsGenerator(self.history, self.pattern_learner)

        # ── Resilience ───────────────────────────────
        from resilience.resilience import HealthCheck, GracefulDegradation, NetworkAware
        self.network = NetworkAware()
        self.health = HealthCheck(self.config)
        self.degradation = GracefulDegradation()

        # ── Deployment operations ───────────────────
        from operations.deploy_manager import DeployManager
        from operations.browser_access import BrowserAccessManager
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
        self.ui = NeuroShellUI()
        self.dashboard = Dashboard(
            history_store=self.history,
            metrics_tracker=self.metrics,
            project_detector=self.project_detector,
            config=self.config,
        )

        # ── Session state ────────────────────────────
        self.session_id = uuid.uuid4().hex[:8]
        self._last_error_output = ""
        self._last_command = ""
        self._running = True
        self._command_count = 0

        # ── Conversation memory for follow-ups ──
        self._conversation_context = []  # last N (input, command, result) tuples
        self._MAX_MEMORY = 5
        self._FOLLOWUP_WORDS = {
            "now", "also", "then", "those", "that", "these",
            "same", "again", "instead", "but", "and", "plus",
            "filter", "sort", "only", "except", "without",
        }

    # ═══════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════

    def startup(self):
        """Run startup sequence with signal handling."""
        self.logger.info("startup", session_id=self.session_id)

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        atexit.register(self._crash_cleanup)

        # Print startup banner
        from ui.banner import render_startup_banner
        print(render_startup_banner(self.config))

        # Fast start mode: skip heavy initialization
        fast_start = os.environ.get("NEUROSHELL_FAST_START") == "1"

        if not fast_start:
            # Run health checks
            report = self.health.run_all()
            self.ui.print_health_report(report)

            # Initialize NLP layer
            self._init_nlp()

            # Pre-warm LLM model in background for faster first response
            self.llm.warmup_async()

            # Initialize learning
            try:
                self.pattern_learner.learn_from_history()
                self.predictor.train()
            except Exception as e:
                self.logger.warn("learning_init_failed", error=str(e))
        else:
            # Minimal init for fast start
            self._init_nlp()
            self.ui.print_info("⚡ Fast start mode — health checks skipped")

        # Check graceful degradation (only warn about Ollama if actually using it)
        provider = getattr(getattr(self.config, 'llm', None), 'provider', 'ollama')
        if provider == "ollama":
            self.degradation.check_and_degrade(
                "ollama", self.llm.is_available(),
                "⚠️ Ollama not available — AI features limited to NLP + cached fixes"
            )
        self.degradation.check_and_degrade(
            "nlp", self.intent_classifier._loaded,
            "⚠️ NLP model not loaded — using regex fallback"
        )

        for warning in self.degradation.get_warnings():
            self.ui.print_info(warning)

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
            # First Ctrl+C cancels current operation, second exits
            if self._command_count > 0:
                print()  # newline after ^C
                return
        self._running = False
        self.shutdown()
        sys.exit(0)

    def _crash_cleanup(self):
        """Atexit handler — save session data even on crash."""
        try:
            self.history.end_session(self.session_id)
        except Exception:
            pass

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

                user_input = input(prompt).strip()
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

        # ── Step 1: NLP Pre-processing (<5ms) ──────
        self.tracer.add_event(cid, "nlp_start")

        # Deterministic prefix routing — always wins over NLP
        lower = user_input.lower().strip()
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
            templates = self.pipeline.list_templates()
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

        if lower.startswith("browser"):
            self._handle_browser_command(user_input)
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

        # ── 2. No smart match — fall back to shell 'start' ──
        import subprocess
        try:
            subprocess.Popen(["cmd.exe", "/c", "start", "", target], shell=False)
            self.ui.print_info(f"  ✅ Attempting to open: {target}")
        except Exception as e:
            self.ui.print_error(f"  ❌ Could not open '{target}': {e}")
            self.ui.print_info(f"  💡 Tip: Type 'fix' to auto-fix that error")

    def _handle_shell_command(self, command: str, cid: str):
        """Execute shell command through safety pipeline."""
        self.tracer.add_event(cid, "safety_check")

        safety = self.safety.check(command)
        policy_tag = self._policy_tag()
        if safety.risk_level in (self._RiskLevel.DANGER, self._RiskLevel.BLOCKED):
            self.ui.print_safety(safety)
            if policy_tag:
                self.ui.print_info(f"  🛡️ Blocked under policy {policy_tag}")
            self.metrics.count("blocked_commands")
            return

        if safety.needs_confirmation:
            self.ui.print_safety(safety)
            if policy_tag:
                self.ui.print_info(f"  🛡️ Confirmation required by policy {policy_tag}")
            if not self.ui.confirm("Execute anyway?"):
                self.metrics.count("user_cancelled")
                return

        # Dependency check
        dep_issues = self.dep_resolver.check_command(command)
        for issue in dep_issues:
            if not issue.is_available:
                self.ui.print_info(f"  ⚠️ {issue.message}")
                if issue.fix_command:
                    self.ui.print_info(f"  💡 Fix: {issue.fix_command}")

        # Network check
        net_warning = self.network.warn_if_offline(command)
        if net_warning:
            self.ui.print_info(net_warning)

        # Execute with spinner for potentially slow commands
        self.tracer.add_event(cid, "execute")
        result = self.executor.execute(
            command,
            stream_callback=lambda line: print(line),
            capture_snapshot=safety.risk_level == self._RiskLevel.CAUTION,
        )

        self._last_command = command
        self.metrics.count("commands_executed")

        # Parse and highlight output
        language_hint = ""
        parsed_output = None
        if result.stdout:
            parsed_output = self.parser.parse(result.stdout)
            self.tracer.add_event(cid, "parsed", output_type=parsed_output.output_type.value)
            language_hint = parsed_output.language_hint if hasattr(parsed_output, 'language_hint') else ""

        # Display result with syntax highlighting
        self.ui.print_result(command, result, language_hint=language_hint, parsed_output=parsed_output)

        # Store in history
        from core.history import CommandRecord
        record = CommandRecord(
            command=command,
            exit_code=result.exit_code,
            stdout_preview=result.stdout[:500],
            stderr_preview=result.stderr[:200],
            cwd=os.getcwd(),
            shell=result.shell,
            duration_ms=result.duration_ms,
            session_id=self.session_id,
        )
        self.history.add_command(record)

        # Record in conversation memory for follow-ups
        self._conversation_context.append({
            'input': command,
            'command': command,
            'output': (result.stdout or result.stderr or '')[:300],
        })
        if len(self._conversation_context) > self._MAX_MEMORY:
            self._conversation_context.pop(0)

        # Handle errors
        if result.exit_code != 0:
            self._last_error_output = result.stderr or result.stdout
            self.sentiment.record_error()
            hint = self.help.get_hint("first_error")
            if hint:
                self.ui.print_hint(hint)
        else:
            self._last_error_output = ""

        self.tracer.add_event(cid, "complete", exit_code=result.exit_code)

    def _handle_natural_language(self, user_input: str, entities, intent, cid: str):

        # ---- v5.0 Offline/PII Hooks ----
        if getattr(self.config, 'raw_shell_mode', False):
            # No-LLM mode
            res = self.phrase_dict.match(user_input)
            if res['confidence'] > 0.8:
                return self._handle_shell_command(res['command'], cid)
            else:
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
            self.ui.print_info(f"  ❌ Invalid alias (empty or recursive)")

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
    # Shutdown
    # ═══════════════════════════════════════════════════════

    def shutdown(self):
        """Graceful shutdown with session summary."""
        self.logger.info("shutdown", session_id=self.session_id)

        # Session summary with timer stats
        session_state = self.sentiment.get_session_state()
        print(self.command_timer.get_formatted_stats(self.metrics))
        self.ui.print_info(f"📊 Provenance: {self.provenance.get_summary()}")

        # Show env changes
        env_changes = self.env_manager.get_session_changes()
        if env_changes["set"] or env_changes["unset"]:
            self.ui.print_info(f"🔧 Env changes: {len(env_changes['set'])} set, {len(env_changes['unset'])} unset")

        if session_state.get("error_rate", 0) > 0.5:
            self.ui.toast("High error rate this session — consider reviewing your workflow", "warning")

        self.ui.print_info("👋 Goodbye from NeuroShell!")
        self.history.end_session(self.session_id)

        # Log performance stats
        perf = self.logger.get_perf_stats()
        if perf.get("total_traces", 0) > 0:
            self.logger.info("session_perf_stats", **perf)


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
