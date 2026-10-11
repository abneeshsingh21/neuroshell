"""
Unit tests for Dynamic GitHub Identity, CLI resolution, and Smart Open integration.
"""

import json
import unittest
from unittest.mock import patch, MagicMock

from operations.github_access import (
    GitHubIdentity,
    GitHubIdentityResolver,
    get_github_identity,
    get_github_install_command,
)
from intelligence.smart_open import SmartOpenEngine
from intelligence.translator import Translator


class TestGitHubDynamicIntegration(unittest.TestCase):
    """Tests dynamic GitHub profile and repo resolution."""

    def setUp(self):
        GitHubIdentityResolver.clear_cache()

    def tearDown(self):
        GitHubIdentityResolver.clear_cache()

    @patch("operations.github_access.GitHubAccessManager._gh_path", return_value="C:\\Program Files\\GitHub CLI\\gh.exe")
    @patch("subprocess.run")
    def test_authenticated_gh_identity(self, mock_run, mock_gh_path):
        """gh api user output successfully populates GitHubIdentity."""
        user_data = {
            "login": "octocat",
            "name": "The Octocat",
            "html_url": "https://github.com/octocat",
        }
        # First call is gh --version, second call is gh api user
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="gh version 2.67.0 (2025-01-01)\n", stderr=""),
            MagicMock(returncode=0, stdout=json.dumps(user_data), stderr=""),
        ]

        identity = GitHubIdentityResolver.resolve(force_refresh=True)
        self.assertTrue(identity.cli_installed)
        self.assertTrue(identity.authenticated)
        self.assertEqual(identity.username, "octocat")
        self.assertEqual(identity.profile_url, "https://github.com/octocat")

    @patch("operations.github_access.GitHubAccessManager._gh_path", return_value=None)
    @patch("subprocess.run")
    def test_git_remote_fallback_when_no_gh(self, mock_run, mock_gh_path):
        """When gh is absent, extract username from git remote origin."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/devuser/my-project.git\n",
            stderr="",
        )

        identity = GitHubIdentityResolver.resolve(force_refresh=True)
        self.assertFalse(identity.cli_installed)
        self.assertEqual(identity.username, "devuser")
        self.assertEqual(identity.profile_url, "https://github.com/devuser")

    @patch("platform.system", return_value="Windows")
    def test_install_command_windows(self, _):
        """Windows install command uses winget."""
        cmd = get_github_install_command()
        self.assertIn("winget install --id GitHub.cli", cmd)

    @patch("operations.github_access.GitHubIdentityResolver.resolve")
    def test_smart_open_dynamic_profile(self, mock_resolve):
        """SmartOpenEngine resolves 'open my github profile' dynamically."""
        mock_resolve.return_value = GitHubIdentity(
            username="alice",
            profile_url="https://github.com/alice",
            display_name="Alice Developer",
            authenticated=True,
            cli_installed=True,
        )

        engine = SmartOpenEngine()
        result = engine.try_resolve("open my github profile")
        self.assertIsNotNone(result)
        self.assertEqual(result.target_type, "url")
        self.assertIn("alice", result.command)

    @patch("operations.github_access.GitHubIdentityResolver.resolve")
    def test_smart_open_dynamic_repos_with_cli(self, mock_resolve):
        """When gh is authenticated, 'open my github repos' yields gh repo list."""
        mock_resolve.return_value = GitHubIdentity(
            username="bob",
            profile_url="https://github.com/bob",
            display_name="Bob",
            authenticated=True,
            cli_installed=True,
        )

        engine = SmartOpenEngine()
        result = engine.try_resolve("open my github repos")
        self.assertIsNotNone(result)
        self.assertEqual(result.command, "gh repo list --limit 15")

    @patch("operations.github_access.GitHubIdentityResolver.resolve")
    def test_translator_dynamic_profile_pattern(self, mock_resolve):
        """Translator resolves 'show mine github profile' via dynamic patterns."""
        mock_resolve.return_value = GitHubIdentity(
            username="charlie",
            profile_url="https://github.com/charlie",
            display_name="Charlie",
            authenticated=True,
            cli_installed=True,
        )

        llm = MagicMock()
        context = MagicMock()
        history = MagicMock()
        context.get_context_summary.return_value = "os=Windows"
        history.search_commands.return_value = []
        history.get_recent.return_value = []

        translator = Translator(llm, context, history)
        result = translator.translate("show mine github profile")
        self.assertEqual(result.source, "local")
        self.assertIn("charlie", result.command)
        # LLM should not have been called because local pattern matched
        llm.generate.assert_not_called()

    @patch("operations.github_access.GitHubIdentityResolver.resolve")
    def test_translator_dynamic_repos_pattern(self, mock_resolve):
        """Translator resolves 'show github repos' to gh repo list."""
        mock_resolve.return_value = GitHubIdentity(
            username="dave",
            profile_url="https://github.com/dave",
            display_name="Dave",
            authenticated=True,
            cli_installed=True,
        )

        llm = MagicMock()
        context = MagicMock()
        history = MagicMock()
        context.get_context_summary.return_value = "os=Windows"
        history.search_commands.return_value = []
        history.get_recent.return_value = []

        translator = Translator(llm, context, history)
        result = translator.translate("show github repos")
        self.assertEqual(result.source, "local")
        self.assertEqual(result.command, "gh repo list --limit 15")
        llm.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
