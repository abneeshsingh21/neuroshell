"""
test_executor.py — Unit tests for core/executor.py

Covers:
- Secondary injection guard (_check_injection)
- Null byte / newline smuggling / backtick / $(...) detection
- Legitimate commands are NOT blocked
- Safe command execution (echo)
"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture()
def executor(mock_config):
    from core.executor import ShellExecutor
    return ShellExecutor(mock_config)


# ─── Injection Guard ─────────────────────────────────────────

class TestInjectionGuard:
    """_check_injection must block dangerous patterns and allow legitimate commands."""

    SAFE_COMMANDS = [
        "echo hello",
        "git status",
        "ls -la",
        "python --version",
        "pip install requests",
        "dir /s",
        "cat README.md",
        "grep -r TODO .",
        "find . -name '*.py'",
        "curl https://api.example.com/data",
        # Pipe is fine — the guard only catches subshell injection
        "netstat | grep 8080",
        "ls | sort",
    ]

    BLOCKED_COMMANDS = [
        ("hello\x00world",          "null byte"),
        ("echo hi\nrm -rf /",       "newline smuggling"),
        ("echo `rm -rf /`",         "backtick subshell"),
        ("echo $(cat /etc/passwd)", "$(...) subshell"),
        ("curl $(evil.com)",        "$(...) subshell"),
        ("ls\r\nrm -rf /",         "carriage return"),
    ]

    def test_safe_commands_not_blocked(self, executor):
        for cmd in self.SAFE_COMMANDS:
            result = executor._check_injection(cmd)
            assert result is None, (
                f"Safe command incorrectly blocked: {cmd!r}\nReason: {result}"
            )

    @pytest.mark.parametrize("cmd,description", BLOCKED_COMMANDS)
    def test_injection_patterns_blocked(self, executor, cmd, description):
        result = executor._check_injection(cmd)
        assert result is not None, (
            f"Injection pattern '{description}' was NOT blocked for cmd: {cmd!r}"
        )
        assert "Security" in result or "blocked" in result.lower()

    def test_blocked_command_returns_error_result(self, executor):
        """Check that execute() returns an error result without spawning a process."""
        result = executor.execute("echo `id`")
        assert result.exit_code != 0 or "blocked" in result.stderr.lower() or "Security" in result.stderr


# ─── Basic Execution ─────────────────────────────────────────

class TestBasicExecution:
    def test_echo_succeeds(self, executor):
        result = executor.execute("echo neuroshell_test_ok")
        assert result.exit_code == 0
        assert "neuroshell_test_ok" in result.stdout

    def test_invalid_command_returns_nonzero(self, executor):
        result = executor.execute("this_command_does_not_exist_qzx")
        assert result.exit_code != 0

    def test_result_has_duration(self, executor):
        result = executor.execute("echo timing")
        assert result.duration_ms >= 0

    def test_result_has_cwd(self, executor):
        result = executor.execute("echo hello")
        assert result.cwd != ""

    def test_timeout_respected(self, executor):
        """Sleep 5s with timeout=1 should result in timeout status."""
        import platform
        if platform.system() == "Windows":
            result = executor.execute("timeout /t 5", timeout=1)
        else:
            result = executor.execute("sleep 5", timeout=1)
        assert result.was_timeout or result.exit_code != 0


# ─── Directory Handling ──────────────────────────────────────

class TestDirectoryHandling:
    def test_cd_changes_cwd(self, executor, tmp_path):
        executor.execute(f'cd "{tmp_path}"')
        assert str(tmp_path) == executor.cwd or tmp_path.name in executor.cwd

    def test_cd_nonexistent_returns_error(self, executor):
        result = executor.execute("cd /this/path/does/not/exist/xyz")
        assert result.exit_code != 0
