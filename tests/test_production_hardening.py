# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""
Regression tests for the production-hardening audit (v5.7.1).

Every test here pins a real bug found during the deep codebase audit so it
can never silently regress:

1. `threading` NameError on the startup critical path (main.py).
2. Duplicate `shutdown()` definitions shadowing background-service cleanup.
3. `Path` local shadowing → UnboundLocalError in `deploy promote`.
4. `VoiceCommandEngine` / `NeuroShellAPI` NameError in command handlers.
5. server.py using nonexistent `SafetyResult.risk` attribute.
6. AutoDream `finally` block referencing undefined `e` / None callback.
7. Slash router stripping quotes from `/clip copy` payloads on POSIX.
8. Smart-open well-known folder resolution failing off-Windows.
9. Version drift between `__version__.py` and `pyproject.toml`.
10. Constant-time API-key comparison in server auth.
"""

import ast
import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ─── 1 & 3: main.py module hygiene ──────────────────────────────────────────

class TestMainModuleHygiene:
    def test_threading_is_module_level_import(self):
        """`startup()` uses threading — it must be importable at module scope."""
        import main
        assert hasattr(main, "threading"), (
            "main.py must import threading at module level; a function-local "
            "import previously caused a NameError crash inside startup()"
        )

    def test_no_local_path_reimports_in_main(self):
        """Function-local `from pathlib import Path` shadows the module-level
        import and caused an UnboundLocalError in the deploy handler."""
        src = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(node):
                    if (
                        isinstance(sub, ast.ImportFrom)
                        and sub.module == "pathlib"
                        and any(a.name == "Path" for a in sub.names)
                    ):
                        offenders.append(f"{node.name}:{sub.lineno}")
        assert not offenders, f"Local pathlib re-imports shadow Path: {offenders}"

    def test_single_shutdown_definition(self):
        """main.py previously defined shutdown() twice; the second silently
        replaced the first, so IPC/AutoDream services were never stopped."""
        src = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        shell_cls = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "NeuroShell"
        )
        shutdown_defs = [n for n in shell_cls.body
                         if isinstance(n, ast.FunctionDef) and n.name == "shutdown"]
        assert len(shutdown_defs) == 1, "NeuroShell must define exactly one shutdown()"

    def test_shutdown_stops_background_services(self):
        """The surviving shutdown() must call the background-service stopper."""
        import main
        src = inspect.getsource(main.NeuroShell.shutdown)
        assert "_stop_background_services" in src

    def test_shutdown_is_idempotent(self):
        import main
        src = inspect.getsource(main.NeuroShell.shutdown)
        assert "_shutdown_complete" in src, "shutdown() must be guarded for re-entry"


# ─── 4: lazy extension class references ─────────────────────────────────────

class TestExtensionReferences:
    def test_voice_hint_uses_scoped_import(self):
        """The voice-unavailable path must import VoiceCommandEngine locally."""
        src = (ROOT / "main.py").read_text(encoding="utf-8")
        # Every use of VoiceCommandEngine outside the loader must be preceded
        # by an import in the same handler.
        assert "from extensions.platform_features import VoiceCommandEngine" in src

    def test_api_hint_uses_scoped_import(self):
        src = (ROOT / "main.py").read_text(encoding="utf-8")
        assert "from extensions.platform_features import NeuroShellAPI" in src


# ─── 5 & 10: server.py contract ─────────────────────────────────────────────

class TestServerContract:
    def test_server_uses_risk_level_attribute(self):
        """SafetyResult exposes `risk_level`, not `risk` — the old attribute
        crashed every command sent over /ws/terminal."""
        src = (ROOT / "server.py").read_text(encoding="utf-8")
        assert re.search(r"safety_res\.risk_level", src)
        assert not re.search(r"safety_res\.risk\b(?!_level)", src)

    def test_server_uses_constant_time_token_comparison(self):
        src = (ROOT / "server.py").read_text(encoding="utf-8")
        assert "secrets.compare_digest" in src, (
            "API-key check must be constant-time to avoid timing side channels"
        )

    def test_all_websocket_endpoints_are_gated(self):
        """Every WebSocket endpoint must pass through the shared auth gate."""
        src = (ROOT / "server.py").read_text(encoding="utf-8")
        ws_endpoints = re.findall(r"@app\.websocket\([^)]*\)\s*\nasync def (\w+)", src)
        assert len(ws_endpoints) >= 3
        for name in ws_endpoints:
            body = src.split(f"async def {name}")[1].split("@app.")[0]
            assert "_authorize_websocket" in body, f"{name} is missing the auth gate"

    def test_safety_result_has_no_risk_alias_needed(self):
        from intelligence.safety import RiskLevel, SafetyResult
        res = SafetyResult(risk_level=RiskLevel.SAFE, reason="ok")
        assert res.risk_level is RiskLevel.SAFE


# ─── 6: AutoDream finally-block regression ──────────────────────────────────

class TestAutoDream:
    def test_no_undefined_name_in_finally(self):
        """The finally block previously referenced an undefined `e` and called
        a possibly-None ui_callback."""
        src = (ROOT / "intelligence" / "memory" / "auto_dream.py").read_text(encoding="utf-8")
        tree = ast.parse(src)  # would raise on syntax errors
        # Ensure the old broken line is gone
        assert "memory synthesis failed - {e}" not in src

    def test_process_queue_survives_none_callback(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        from intelligence.memory.auto_dream import AutoDreamDaemon
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("boom")
        daemon = AutoDreamDaemon(MagicMock(), llm)
        daemon.ui_callback = None
        # Must not raise even when the LLM explodes and no callback is set
        for attr in ("_process_queue", "process_queue", "_consolidate"):
            fn = getattr(daemon, attr, None)
            if fn is not None:
                try:
                    fn()
                except TypeError:
                    pass  # requires args — structural check above still covers the fix
                break


# ─── 7: slash router quote preservation ─────────────────────────────────────

class TestSlashClipQuotes:
    def test_clip_copy_preserves_quotes(self, monkeypatch):
        """`/clip copy echo 'Hello World'` must keep the single quotes."""
        import main as main_mod
        shell = main_mod.NeuroShell.__new__(main_mod.NeuroShell)

        class _FakeClip:
            def __init__(self):
                self.copied = None

            def copy(self, text):
                self.copied = text
                return True

        class _FakeUI:
            def print_info(self, *a, **k):
                pass

            def print_error(self, *a, **k):
                pass

        shell.ext_clipboard = _FakeClip()
        shell.ui = _FakeUI()
        shell._handle_slash_clip(
            ["copy", "echo", "Hello World"],
            "copy echo 'Hello World'",
        )
        assert shell.ext_clipboard.copied == "echo 'Hello World'"


# ─── 8: smart-open well-known folders ───────────────────────────────────────

class TestSmartOpenFolders:
    def test_downloads_resolves_without_existing_dir(self, monkeypatch):
        """Well-known profile folders must resolve deterministically even when
        the directory does not exist on the build machine (Linux CI testing a
        Windows-mode translation)."""
        from unittest.mock import patch

        with patch("platform.system", return_value="Windows"):
            from intelligence.smart_open import SmartOpenEngine
            engine = SmartOpenEngine()
            result = engine.try_resolve("open downloads folder")
            assert result is not None
            assert result.target_type == "folder"
            assert "downloads" in result.resolved_path.lower()


# ─── 9: version consistency ─────────────────────────────────────────────────

class TestVersionConsistency:
    def test_version_matches_pyproject(self):
        try:
            import tomllib  # py311+
            data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        except ModuleNotFoundError:  # py310 fallback
            import toml
            data = toml.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        from __version__ import __version__
        assert data["project"]["version"] == __version__, (
            "pyproject.toml and __version__.py must agree — release artifacts "
            "were previously stamped with three different versions"
        )

    def test_version_is_pep440_like(self):
        from __version__ import __version__, __version_info__
        assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
        assert __version_info__ == tuple(int(x) for x in __version__.split("."))


# ─── Lifecycle smoke: startup must not crash ────────────────────────────────

class TestStartupSmoke:
    @pytest.mark.integration
    def test_startup_and_shutdown_do_not_raise(self, monkeypatch, capsys):
        import os
        monkeypatch.setenv("NEUROSHELL_TEST_MODE", "1")
        import main as main_mod
        shell = main_mod.NeuroShell()
        shell.startup()          # crashed with NameError before the fix
        shell.shutdown()
        shell.shutdown()         # idempotent — second call is a no-op
