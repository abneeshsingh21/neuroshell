"""
NeuroShell Unit Tests — Core Engine
Comprehensive tests for executor, context, history, output_parser, dependency_resolver.
"""

import os
import sys
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestShellExecutor(unittest.TestCase):
    """Tests for core/executor.py."""

    def setUp(self):
        from config import Config
        from core.executor import ShellExecutor
        self.config = Config.load()
        self.executor = ShellExecutor(self.config)

    def test_basic_command(self):
        """Test basic command execution."""
        result = self.executor.execute("echo hello")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hello", result.stdout)

    def test_failed_command(self):
        """Test handling of failed commands."""
        result = self.executor.execute('python -c "import sys; sys.exit(1)"')
        self.assertNotEqual(result.exit_code, 0)

    def test_duration_tracking(self):
        """Test that duration is tracked."""
        result = self.executor.execute("echo test")
        self.assertGreater(result.duration_ms, 0)

    def test_cwd_tracking(self):
        """Test that current directory is tracked."""
        self.assertIsNotNone(self.executor.cwd)

    def test_stream_callback(self):
        """Test streaming output callback."""
        lines = []
        result = self.executor.execute(
            "echo test_stream",
            stream_callback=lambda line: lines.append(line),
        )
        self.assertEqual(result.exit_code, 0)

    def test_result_has_shell(self):
        """Test that result tracks which shell was used."""
        result = self.executor.execute("echo test")
        self.assertIsNotNone(result.shell)
        self.assertTrue(len(result.shell) > 0)


class TestOutputParser(unittest.TestCase):
    """Tests for core/output_parser.py."""

    def setUp(self):
        from core.output_parser import OutputParser, OutputType
        self.parser = OutputParser()
        self.OutputType = OutputType

    def test_json_detection(self):
        """Test JSON output detection."""
        output = '{"key": "value", "number": 42}'
        result = self.parser.parse(output)
        self.assertEqual(result.output_type, self.OutputType.JSON_DATA)

    def test_json_array(self):
        """Test JSON array detection."""
        output = '[{"id": 1}, {"id": 2}]'
        result = self.parser.parse(output)
        self.assertEqual(result.output_type, self.OutputType.JSON_DATA)

    def test_plain_text(self):
        """Test plain text detection."""
        result = self.parser.parse("Hello, World!")
        self.assertEqual(result.output_type, self.OutputType.PLAIN)

    def test_empty_output(self):
        """Test empty output handling."""
        result = self.parser.parse("")
        self.assertEqual(result.output_type, self.OutputType.EMPTY)

    def test_stack_trace_python(self):
        """Test Python stack trace detection."""
        trace = '''Traceback (most recent call last):
  File "test.py", line 10, in <module>
    raise ValueError("test")
ValueError: test'''
        result = self.parser.parse(trace)
        self.assertEqual(result.output_type, self.OutputType.STACK_TRACE)

    def test_csv_detection(self):
        """Test CSV detection."""
        csv_data = "name,age,city\nAlice,30,NYC\nBob,25,LA"
        result = self.parser.parse(csv_data)
        self.assertEqual(result.output_type, self.OutputType.CSV)

    def test_line_count(self):
        """Test line count accuracy."""
        output = "line1\nline2\nline3"
        result = self.parser.parse(output)
        self.assertEqual(result.line_count, 3)

    def test_log_detection(self):
        """Test log output detection."""
        log = "2024-01-01 10:00:00 INFO Starting app\n2024-01-01 10:00:01 ERROR Failed connect\n2024-01-01 10:00:02 INFO Retrying"
        result = self.parser.parse(log)
        self.assertEqual(result.output_type, self.OutputType.LOG)

    def test_xml_detection(self):
        """Test XML output detection."""
        xml = '<?xml version="1.0"?>\n<root><item>test</item></root>'
        result = self.parser.parse(xml)
        self.assertEqual(result.output_type, self.OutputType.XML_DATA)

    def test_large_output_limit(self):
        """Test that the parser handles large output gracefully."""
        large = "x" * 2_000_000
        result = self.parser.parse(large)
        self.assertIsNotNone(result)


class TestHistoryStore(unittest.TestCase):
    """Tests for core/history.py."""

    def setUp(self):
        from core.history import HistoryStore, CommandRecord
        self.CommandRecord = CommandRecord
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "test_history.db"
        self.history = HistoryStore(db_path=self.db_path)

    def test_add_and_retrieve(self):
        """Test adding and retrieving commands."""
        record = self.CommandRecord(
            command="git status",
            exit_code=0,
            stdout_preview="On branch main",
            stderr_preview="",
            cwd="/test",
            shell="bash",
            duration_ms=50,
            session_id="test123",
        )
        self.history.add_command(record)
        recent = self.history.get_recent(1)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].command, "git status")

    def test_search(self):
        """Test command search."""
        r1 = self.CommandRecord(command="git push origin main", exit_code=0)
        r2 = self.CommandRecord(command="pip install flask", exit_code=0)
        self.history.add_command(r1)
        self.history.add_command(r2)
        results = self.history.search_commands("git")
        self.assertTrue(any("git" in r.command for r in results))

    def test_session_management(self):
        """Test session start/end."""
        self.history.start_session("session_test", "/tmp", "python")
        self.history.end_session("session_test")

    def test_multiple_commands(self):
        """Test adding multiple commands."""
        for i in range(10):
            r = self.CommandRecord(command=f"echo {i}", exit_code=0)
            self.history.add_command(r)
        recent = self.history.get_recent(5)
        self.assertEqual(len(recent), 5)

    def test_failed_command_search(self):
        """Test searching for failed commands."""
        r = self.CommandRecord(command="bad_cmd", exit_code=127, stderr_preview="not found")
        self.history.add_command(r)
        results = self.history.search_commands("bad_cmd")
        self.assertTrue(len(results) > 0)


class TestDependencyResolver(unittest.TestCase):
    """Tests for core/dependency_resolver.py."""

    def setUp(self):
        from config import Config
        from core.context import ContextManager
        from core.dependency_resolver import DependencyResolver
        config = Config.load()
        ctx = ContextManager(config)
        self.resolver = DependencyResolver(ctx)

    def test_builtin_check(self):
        """Test that builtins are recognized."""
        self.assertTrue(self.resolver._is_builtin("echo"))
        self.assertTrue(self.resolver._is_builtin("cd"))
        self.assertFalse(self.resolver._is_builtin("unknown_tool"))

    def test_tool_exists(self):
        """Test tool existence check."""
        result = self.resolver._check_tool_exists("python")
        self.assertTrue(result.is_available)

    def test_tool_not_exists(self):
        """Test missing tool detection."""
        result = self.resolver._check_tool_exists("nonexistent_tool_xyz_123")
        self.assertFalse(result.is_available)


class TestContextManager(unittest.TestCase):
    """Tests for core/context.py."""

    def setUp(self):
        from config import Config
        from core.context import ContextManager
        self.config = Config.load()
        self.ctx = ContextManager(self.config)

    def test_context_snapshot(self):
        """Test full context snapshot retrieval."""
        ctx = self.ctx.get_context()
        self.assertIsNotNone(ctx.os_name)
        self.assertIsNotNone(ctx.cwd)

    def test_context_summary(self):
        """Test context summary generation."""
        summary = self.ctx.get_context_summary()
        self.assertIsInstance(summary, str)
        self.assertGreater(len(summary), 0)

    def test_os_detection(self):
        """Test OS name is detected."""
        ctx = self.ctx.get_context()
        self.assertIn(ctx.os_name, ["Windows", "Linux", "Darwin"])


if __name__ == "__main__":
    unittest.main()
