# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Universal Polyglot Code Runner Subsystem for NeuroShell.
Automatically discovers installed compilers, interpreters, and runtime toolchains,
compiles source files when necessary, and executes them with interactive streaming:
- Python (.py)
- C++ (.cpp, .cc, .cxx)
- C (.c)
- Java (.java)
- Rust (.rs)
- Go (.go)
- TypeScript (.ts, .tsx)
- JavaScript (.js, .mjs)
- C# (.cs)
- Kotlin (.kt)
- Dart (.dart)
- Ruby (.rb), PHP (.php), Lua (.lua), Swift (.swift), Zig (.zig)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

# Ensure neuroshell root is on sys.path
_NEUROSHELL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NEUROSHELL_ROOT not in sys.path:
    sys.path.insert(0, _NEUROSHELL_ROOT)

from ui.table_formatter import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_MAGENTA,
    C_RED,
    C_RESET,
    C_WHITE,
    C_YELLOW,
)

_IS_WINDOWS = platform.system() == "Windows"


@dataclass
class ExecutionResult:
    """Outcome of a code execution attempt."""
    success: bool
    exit_code: int
    language: str
    command_executed: str
    output: str = ""
    error: str = ""
    compiler_used: str = ""


class UniversalCodeRunner:
    """
    Intelligent polyglot compilation and execution engine.
    Analyzes file extensions, locates local toolchains, compiles if needed,
    and runs the target program seamlessly.
    """

    LANGUAGE_EXTENSIONS: dict[str, str] = {
        ".py": "python",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c++": "cpp",
        ".c": "c",
        ".java": "java",
        ".rs": "rust",
        ".go": "go",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cs": "csharp",
        ".kt": "kotlin",
        ".dart": "dart",
        ".rb": "ruby",
        ".php": "php",
        ".lua": "lua",
        ".swift": "swift",
        ".zig": "zig",
        ".sh": "bash",
    }

    def __init__(self, cwd: Path | str | None = None):
        self.cwd = Path(cwd) if cwd else Path.cwd()

    def identify_language(self, file_path: Path | str) -> str:
        """Identify programming language from file extension."""
        p = Path(file_path)
        ext = p.suffix.lower()
        return self.LANGUAGE_EXTENSIONS.get(ext, "unknown")

    def _find_python(self) -> str:
        """Find the most specific Python binary (preferring active .venv)."""
        candidates = [
            self.cwd / ".venv" / "Scripts" / "python.exe",
            self.cwd / "venv" / "Scripts" / "python.exe",
            self.cwd / ".venv" / "bin" / "python",
            self.cwd / "venv" / "bin" / "python",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return sys.executable or shutil.which("python") or shutil.which("python3") or "python"

    def _find_cpp_compiler(self) -> tuple[str, str]:
        """Locate available C++ compiler: g++, clang++, or MSVC cl.exe."""
        if shutil.which("g++"):
            return "g++", "gcc"
        if shutil.which("clang++"):
            return "clang++", "clang"
        if shutil.which("cl"):
            return "cl", "msvc"
        return "", ""

    def _find_c_compiler(self) -> tuple[str, str]:
        """Locate available C compiler: gcc, clang, or MSVC cl.exe."""
        if shutil.which("gcc"):
            return "gcc", "gcc"
        if shutil.which("clang"):
            return "clang", "clang"
        if shutil.which("cl"):
            return "cl", "msvc"
        return "", ""

    def run(self, target_file: str, args: list[str] | None = None, interactive: bool = True) -> ExecutionResult:
        """Compile and execute any supported programming language file."""
        args = args or []
        path = (self.cwd / target_file).resolve() if not os.path.isabs(target_file) else Path(target_file).resolve()

        if not path.exists():
            print(f"\n  {C_RED}❌ Source file not found: {C_BOLD}{target_file}{C_RESET}\n")
            return ExecutionResult(
                success=False,
                exit_code=1,
                language="unknown",
                command_executed="",
                error=f"File not found: {target_file}",
            )

        lang = self.identify_language(path)
        if lang == "unknown":
            print(f"\n  {C_YELLOW}⚠ Unknown file extension for: {C_BOLD}{path.name}{C_RESET}\n")
            # Fallback to direct shell execution
            return self._run_command(f'"{path}" {" ".join(args)}', lang="unknown", interactive=interactive)

        print(f"\n  {C_BOLD}{C_CYAN}⚡ Polyglot Runner:{C_RESET} {C_WHITE}{path.name}{C_RESET} [{C_MAGENTA}{lang.upper()}{C_RESET}]")

        if lang == "python":
            return self._run_python(path, args, interactive=interactive)
        elif lang == "cpp":
            return self._run_cpp(path, args, interactive=interactive)
        elif lang == "c":
            return self._run_c(path, args, interactive=interactive)
        elif lang == "java":
            return self._run_java(path, args, interactive=interactive)
        elif lang == "rust":
            return self._run_rust(path, args, interactive=interactive)
        elif lang == "go":
            return self._run_go(path, args, interactive=interactive)
        elif lang == "typescript":
            return self._run_typescript(path, args, interactive=interactive)
        elif lang == "javascript":
            return self._run_javascript(path, args, interactive=interactive)
        elif lang == "csharp":
            return self._run_csharp(path, args, interactive=interactive)
        elif lang == "kotlin":
            return self._run_kotlin(path, args, interactive=interactive)
        elif lang == "dart":
            return self._run_dart(path, args, interactive=interactive)
        elif lang in ("ruby", "php", "lua", "swift", "zig", "bash"):
            return self._run_script_lang(lang, path, args, interactive=interactive)

        return ExecutionResult(False, 1, lang, "", error=f"Unsupported language: {lang}")

    def _run_python(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        py = self._find_python()
        cmd = f'"{py}" "{path}"'
        if args:
            cmd += " " + " ".join(args)
        return self._run_command(cmd, language="python", interactive=interactive)

    def _run_cpp(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        compiler, flavor = self._find_cpp_compiler()
        if not compiler:
            print(f"  {C_RED}❌ No C++ compiler found (g++, clang++, or cl.exe). Install MinGW or Visual Studio C++.{C_RESET}\n")
            return ExecutionResult(False, 1, "cpp", "", error="No C++ compiler found")

        bin_name = path.stem + (".exe" if _IS_WINDOWS else "")
        bin_path = path.parent / bin_name

        print(f"  {C_DIM}Compiling with {compiler} (C++20)...{C_RESET}")
        if flavor in ("gcc", "clang"):
            compile_cmd = [compiler, "-std=c++20", "-O2", str(path), "-o", str(bin_path)]
        else:  # MSVC
            compile_cmd = [compiler, "/EHsc", "/std:c++20", str(path), f"/Fe:{bin_path}"]

        comp_proc = subprocess.run(compile_cmd, cwd=str(path.parent), capture_output=True, text=True)
        if comp_proc.returncode != 0:
            print(f"  {C_RED}❌ Compilation failed:{C_RESET}\n{comp_proc.stderr or comp_proc.stdout}")
            return ExecutionResult(False, comp_proc.returncode, "cpp", " ".join(compile_cmd), error=comp_proc.stderr or comp_proc.stdout, compiler_used=compiler)

        print(f"  {C_GREEN}✔ Compiled successfully → {bin_name}{C_RESET}\n")
        exec_cmd = f'"{bin_path}"'
        if args:
            exec_cmd += " " + " ".join(args)
        return self._run_command(exec_cmd, language="cpp", compiler_used=compiler, interactive=interactive)

    def _run_c(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        compiler, flavor = self._find_c_compiler()
        if not compiler:
            print(f"  {C_RED}❌ No C compiler found (gcc, clang, or cl.exe). Install MinGW or GCC.{C_RESET}\n")
            return ExecutionResult(False, 1, "c", "", error="No C compiler found")

        bin_name = path.stem + (".exe" if _IS_WINDOWS else "")
        bin_path = path.parent / bin_name

        print(f"  {C_DIM}Compiling with {compiler}...{C_RESET}")
        if flavor in ("gcc", "clang"):
            compile_cmd = [compiler, "-O2", str(path), "-o", str(bin_path)]
        else:  # MSVC
            compile_cmd = [compiler, str(path), f"/Fe:{bin_path}"]

        comp_proc = subprocess.run(compile_cmd, cwd=str(path.parent), capture_output=True, text=True)
        if comp_proc.returncode != 0:
            print(f"  {C_RED}❌ Compilation failed:{C_RESET}\n{comp_proc.stderr or comp_proc.stdout}")
            return ExecutionResult(False, comp_proc.returncode, "c", " ".join(compile_cmd), error=comp_proc.stderr or comp_proc.stdout, compiler_used=compiler)

        print(f"  {C_GREEN}✔ Compiled successfully → {bin_name}{C_RESET}\n")
        exec_cmd = f'"{bin_path}"'
        if args:
            exec_cmd += " " + " ".join(args)
        return self._run_command(exec_cmd, language="c", compiler_used=compiler, interactive=interactive)

    def _run_java(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        java = shutil.which("java")
        if not java:
            print(f"  {C_RED}❌ Java runtime not found. Install OpenJDK or Oracle Java.{C_RESET}\n")
            return ExecutionResult(False, 1, "java", "", error="java not found")

        # In Java 11+, single files can be executed directly via `java <file>`
        cmd = f'"{java}" "{path}"'
        if args:
            cmd += " " + " ".join(args)
        return self._run_command(cmd, language="java", compiler_used="java", interactive=interactive)

    def _run_rust(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        # Check if inside a Cargo project
        cargo_toml = path.parent / "Cargo.toml"
        if not cargo_toml.exists() and (self.cwd / "Cargo.toml").exists():
            cargo_toml = self.cwd / "Cargo.toml"

        if cargo_toml.exists() and shutil.which("cargo"):
            cmd = "cargo run"
            if args:
                cmd += " -- " + " ".join(args)
            return self._run_command(cmd, language="rust", compiler_used="cargo", interactive=interactive)

        rustc = shutil.which("rustc")
        if not rustc:
            print(f"  {C_RED}❌ Rust compiler not found. Install Rust via https://rustup.rs{C_RESET}\n")
            return ExecutionResult(False, 1, "rust", "", error="rustc not found")

        bin_name = path.stem + (".exe" if _IS_WINDOWS else "")
        bin_path = path.parent / bin_name

        print(f"  {C_DIM}Compiling with rustc...{C_RESET}")
        comp_proc = subprocess.run([rustc, str(path), "-o", str(bin_path)], cwd=str(path.parent), capture_output=True, text=True)
        if comp_proc.returncode != 0:
            print(f"  {C_RED}❌ Compilation failed:{C_RESET}\n{comp_proc.stderr or comp_proc.stdout}")
            return ExecutionResult(False, comp_proc.returncode, "rust", f"rustc {path.name}", error=comp_proc.stderr, compiler_used="rustc")

        print(f"  {C_GREEN}✔ Compiled successfully → {bin_name}{C_RESET}\n")
        exec_cmd = f'"{bin_path}"'
        if args:
            exec_cmd += " " + " ".join(args)
        return self._run_command(exec_cmd, language="rust", compiler_used="rustc", interactive=interactive)

    def _run_go(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        go = shutil.which("go")
        if not go:
            print(f"  {C_RED}❌ Go compiler not found. Install Go via https://go.dev{C_RESET}\n")
            return ExecutionResult(False, 1, "go", "", error="go not found")

        cmd = f'"{go}" run "{path}"'
        if args:
            cmd += " " + " ".join(args)
        return self._run_command(cmd, language="go", compiler_used="go", interactive=interactive)

    def _run_typescript(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        runner = shutil.which("tsx") or shutil.which("ts-node") or shutil.which("bun") or shutil.which("deno")
        if runner:
            runner_name = Path(runner).stem
            cmd = f'"{runner}" "{path}"' if runner_name != "deno" else f'"{runner}" run -A "{path}"'
        elif shutil.which("npx"):
            cmd = f'npx tsx "{path}"'
        else:
            print(f"  {C_RED}❌ TypeScript runtime not found. Install tsx via 'npm install -g tsx'.{C_RESET}\n")
            return ExecutionResult(False, 1, "typescript", "", error="tsx/ts-node not found")

        if args:
            cmd += " " + " ".join(args)
        return self._run_command(cmd, language="typescript", interactive=interactive)

    def _run_javascript(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        node = shutil.which("node") or shutil.which("bun") or shutil.which("deno")
        if not node:
            print(f"  {C_RED}❌ Node.js not found. Install Node from https://nodejs.org{C_RESET}\n")
            return ExecutionResult(False, 1, "javascript", "", error="node not found")

        cmd = f'"{node}" "{path}"'
        if args:
            cmd += " " + " ".join(args)
        return self._run_command(cmd, language="javascript", interactive=interactive)

    def _run_csharp(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        dotnet = shutil.which("dotnet")
        if not dotnet:
            print(f"  {C_RED}❌ .NET SDK not found. Install .NET SDK from https://dotnet.microsoft.com{C_RESET}\n")
            return ExecutionResult(False, 1, "csharp", "", error="dotnet not found")

        cmd = f'"{dotnet}" run'
        if args:
            cmd += " -- " + " ".join(args)
        return self._run_command(cmd, language="csharp", interactive=interactive)

    def _run_kotlin(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        kotlinc = shutil.which("kotlinc")
        java = shutil.which("java")
        if not kotlinc or not java:
            print(f"  {C_RED}❌ Kotlin compiler (kotlinc) or Java not found.{C_RESET}\n")
            return ExecutionResult(False, 1, "kotlin", "", error="kotlinc not found")

        jar_path = path.parent / (path.stem + ".jar")
        comp = subprocess.run([kotlinc, str(path), "-include-runtime", "-d", str(jar_path)], capture_output=True, text=True)
        if comp.returncode != 0:
            print(f"  {C_RED}❌ Kotlin compilation failed:{C_RESET}\n{comp.stderr}")
            return ExecutionResult(False, comp.returncode, "kotlin", "kotlinc", error=comp.stderr)

        cmd = f'"{java}" -jar "{jar_path}"'
        if args:
            cmd += " " + " ".join(args)
        return self._run_command(cmd, language="kotlin", interactive=interactive)

    def _run_dart(self, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        dart = shutil.which("dart")
        if not dart:
            print(f"  {C_RED}❌ Dart SDK not found. Install Dart from https://dart.dev{C_RESET}\n")
            return ExecutionResult(False, 1, "dart", "", error="dart not found")

        cmd = f'"{dart}" run "{path}"'
        if args:
            cmd += " " + " ".join(args)
        return self._run_command(cmd, language="dart", interactive=interactive)

    def _run_script_lang(self, lang: str, path: Path, args: list[str], interactive: bool = True) -> ExecutionResult:
        binary = shutil.which(lang)
        if not binary:
            print(f"  {C_RED}❌ Runtime for '{lang}' not found on PATH.{C_RESET}\n")
            return ExecutionResult(False, 1, lang, "", error=f"{lang} runtime not found")

        cmd = f'"{binary}" "{path}"'
        if args:
            cmd += " " + " ".join(args)
        return self._run_command(cmd, language=lang, interactive=interactive)

    def _run_command(self, cmd: str, language: str = "", compiler_used: str = "", interactive: bool = True) -> ExecutionResult:
        try:
            if interactive:
                # Direct interactive passthrough for full stdin/stdout terminal fidelity
                proc = subprocess.run(cmd, shell=True, cwd=str(self.cwd))
                success = proc.returncode == 0
                return ExecutionResult(
                    success=success,
                    exit_code=proc.returncode,
                    language=language,
                    command_executed=cmd,
                    compiler_used=compiler_used,
                )
            else:
                proc = subprocess.run(cmd, shell=True, cwd=str(self.cwd), capture_output=True, text=True)
                success = proc.returncode == 0
                return ExecutionResult(
                    success=success,
                    exit_code=proc.returncode,
                    language=language,
                    command_executed=cmd,
                    output=proc.stdout or "",
                    error=proc.stderr or "",
                    compiler_used=compiler_used,
                )
        except Exception as exc:
            print(f"\n  {C_RED}❌ Execution error: {exc}{C_RESET}\n")
            return ExecutionResult(False, 1, language, cmd, error=str(exc), compiler_used=compiler_used)


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    if not raw_args or raw_args[0] in ("-h", "--help"):
        print("usage: code_runner.py file [args ...]\n\nNeuroShell Universal Polyglot Code Runner\n\npositional arguments:\n  file   Source file to compile and execute (e.g. main.py, App.java, main.cpp)\n  args   Optional arguments to forward directly to the program\n")
        return 0

    target_file = raw_args[0]
    child_args = raw_args[1:]

    runner = UniversalCodeRunner()
    result = runner.run(target_file, child_args, interactive=True)
    return 0 if result.success else result.exit_code


if __name__ == "__main__":
    sys.exit(main())
