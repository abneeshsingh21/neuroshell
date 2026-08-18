"""
Regression coverage for recent production hardening in main.py and server.py.
"""

import asyncio
import importlib
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMainRoutingRegressions(unittest.TestCase):
    def _make_shell(self):
        from main import NeuroShell

        shell = NeuroShell.__new__(NeuroShell)
        shell.tracer = MagicMock()
        shell.tracer.start_trace.return_value = "cid-123"
        shell.metrics = MagicMock()
        shell._command_count = 0
        shell._degraded = False
        shell.ui = MagicMock()
        return shell

    def test_pipelines_command_uses_pipeline_builder(self):
        shell = self._make_shell()
        shell.pipeline_builder = MagicMock()
        shell.pipeline_builder.list_templates.return_value = ["alpha", "beta"]

        with patch("builtins.print") as mock_print:
            shell.process_input("pipelines")

        shell.pipeline_builder.list_templates.assert_called_once_with()
        shell.tracer.end_trace.assert_called_once_with("cid-123")
        rendered = " ".join(
            " ".join(str(arg) for arg in call.args)
            for call in mock_print.call_args_list
        )
        self.assertIn("alpha", rendered)
        self.assertIn("beta", rendered)
        self.assertIn("Total: 2 templates", rendered)

    def test_pipelines_command_handles_missing_builder_gracefully(self):
        shell = self._make_shell()

        shell.process_input("pipelines")

        shell.ui.print_error.assert_called_once()
        self.assertIn(
            "Pipeline builder unavailable",
            shell.ui.print_error.call_args.args[0],
        )
        shell.tracer.end_trace.assert_called_once_with("cid-123")

    def test_raw_shell_mode_uses_phrase_dictionary_translate(self):
        shell = self._make_shell()
        shell.config = SimpleNamespace(raw_shell_mode=True)
        shell.phrase_dict = MagicMock()
        shell.phrase_dict.translate.return_value = {
            "command": "dir",
            "confidence": 0.95,
        }
        shell._handle_shell_command = MagicMock()

        shell._handle_natural_language(
            "list files",
            entities=MagicMock(),
            intent=MagicMock(),
            cid="cid-raw",
        )

        shell.phrase_dict.translate.assert_called_once_with("list files")
        shell._handle_shell_command.assert_called_once_with("dir", "cid-raw")
        shell.ui.print_error.assert_not_called()

    def test_raw_shell_mode_reports_when_dictionary_has_no_match(self):
        shell = self._make_shell()
        shell.config = SimpleNamespace(raw_shell_mode=True)
        shell.phrase_dict = MagicMock()
        shell.phrase_dict.translate.return_value = None
        shell._handle_shell_command = MagicMock()

        shell._handle_natural_language(
            "unknown request",
            entities=MagicMock(),
            intent=MagicMock(),
            cid="cid-raw",
        )

        shell.ui.print_error.assert_called_once()
        self.assertIn("Raw Shell Mode", shell.ui.print_error.call_args.args[0])
        shell._handle_shell_command.assert_not_called()


class TestServerProductionHardening(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("server", None)

    def _import_server(self):
        def _package(name: str) -> types.ModuleType:
            pkg = types.ModuleType(name)
            pkg.__path__ = []
            return pkg

        fake_fastapi = _package("fastapi")

        class FakeFastAPI:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def add_middleware(self, *args, **kwargs):
                return None

            def mount(self, *args, **kwargs):
                return None

            def get(self, _path):
                def decorator(fn):
                    return fn
                return decorator

            def websocket(self, _path):
                def decorator(fn):
                    return fn
                return decorator

        fake_fastapi.FastAPI = FakeFastAPI
        fake_fastapi.WebSocket = object
        fake_fastapi.WebSocketDisconnect = type(
            "WebSocketDisconnect", (Exception,), {}
        )

        cors_mod = types.ModuleType("fastapi.middleware.cors")
        cors_mod.CORSMiddleware = object

        staticfiles_mod = types.ModuleType("fastapi.staticfiles")

        class FakeStaticFiles:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        staticfiles_mod.StaticFiles = FakeStaticFiles

        responses_mod = types.ModuleType("fastapi.responses")

        class FakeFileResponse:
            def __init__(self, path, headers=None, **kwargs):
                self.path = path
                self.headers = headers or {}
                self.kwargs = kwargs

        class FakeJSONResponse:
            def __init__(self, *args, **kwargs):
                self.status_code = kwargs.get("status_code")
                self.content = kwargs.get("content")

        responses_mod.FileResponse = FakeFileResponse
        responses_mod.JSONResponse = FakeJSONResponse

        uvicorn_mod = types.ModuleType("uvicorn")
        uvicorn_mod.run = MagicMock()

        psutil_mod = types.ModuleType("psutil")
        psutil_mod.process_iter = MagicMock(return_value=[])
        psutil_mod.cpu_percent = MagicMock(return_value=0.0)
        psutil_mod.virtual_memory = MagicMock(
            return_value=SimpleNamespace(percent=0.0)
        )
        psutil_mod.disk_usage = MagicMock(
            return_value=SimpleNamespace(percent=0.0)
        )
        psutil_mod.NoSuchProcess = Exception
        psutil_mod.AccessDenied = Exception

        config_mod = types.ModuleType("config")
        config_mod.load_config = MagicMock(
            return_value=SimpleNamespace(default_shell="powershell")
        )

        llm_pkg = _package("llm")
        llm_client_mod = types.ModuleType("llm.client")
        llm_client_mod.LLMClient = MagicMock()

        intelligence_pkg = _package("intelligence")
        translator_mod = types.ModuleType("intelligence.translator")
        translator_mod.Translator = MagicMock()

        core_pkg = _package("core")
        executor_mod = types.ModuleType("core.executor")
        executor_mod.ShellExecutor = MagicMock()
        context_mod = types.ModuleType("core.context")
        context_mod.ContextManager = MagicMock()
        history_mod = types.ModuleType("core.history")

        class FakeHistoryStore:
            def __init__(self, *args, **kwargs):
                self._history = []

            def get_stats(self):
                return {}

        history_mod.HistoryStore = FakeHistoryStore

        events_mod = types.ModuleType("core.events")
        events_mod.neuro_events = SimpleNamespace(
            subscribe=MagicMock(),
            unsubscribe=MagicMock(),
        )

        fake_modules = {
            "fastapi": fake_fastapi,
            "fastapi.middleware": _package("fastapi.middleware"),
            "fastapi.middleware.cors": cors_mod,
            "fastapi.staticfiles": staticfiles_mod,
            "fastapi.responses": responses_mod,
            "uvicorn": uvicorn_mod,
            "psutil": psutil_mod,
            "config": config_mod,
            "llm": llm_pkg,
            "llm.client": llm_client_mod,
            "intelligence": intelligence_pkg,
            "intelligence.translator": translator_mod,
            "core": core_pkg,
            "core.executor": executor_mod,
            "core.context": context_mod,
            "core.history": history_mod,
            "core.events": events_mod,
        }

        with patch.dict(sys.modules, fake_modules, clear=False):
            sys.modules.pop("server", None)
            return importlib.import_module("server")

    def test_dashboard_api_uses_config_object_and_history_stats(self):
        server = self._import_server()
        server.config = SimpleNamespace(default_shell="pwsh")
        server.history = SimpleNamespace(
            get_stats=lambda: {"total_commands": 17},
            _history=[1, 2, 3],
        )

        payload = asyncio.run(server.dashboard_api())

        self.assertEqual(payload["shell"], "Pwsh")
        self.assertEqual(payload["history"], 17)

    def test_dashboard_history_count_falls_back_to_buffer(self):
        server = self._import_server()

        class BrokenHistory:
            def __init__(self):
                self._history = [1, 2, 3, 4]

            def get_stats(self):
                raise RuntimeError("stats unavailable")

        server.history = BrokenHistory()

        self.assertEqual(server._dashboard_history_count(), 4)

    def test_serve_frontend_returns_json_when_build_is_missing(self):
        server = self._import_server()

        class MissingIndex:
            def exists(self):
                return False

        server._FRONTEND_INDEX_FILE = MissingIndex()
        response = asyncio.run(server.serve_frontend())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content["status"], "frontend_unavailable")


if __name__ == "__main__":
    unittest.main()
