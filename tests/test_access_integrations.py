import unittest
import tempfile
from pathlib import Path

from operations.browser_access import BrowserAccessManager
from operations.github_access import GitHubAccessManager


class TestBrowserAccess(unittest.TestCase):
    def setUp(self):
        self.manager = BrowserAccessManager(Path.cwd())

    def test_status_shape(self):
        status = self.manager.status()
        self.assertIn("playwright_installed", status)
        self.assertIn("fetch_ready", status)

    def test_invalid_url_rejected(self):
        with self.assertRaises(ValueError):
            self.manager.fetch_html("example.com")


class TestGithubAccess(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        context = Path(self.temp_dir.name) / "github_context.json"
        self.manager = GitHubAccessManager(Path.cwd(), context_file=context)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_status_shape(self):
        status = self.manager.status()
        self.assertIn("gh_installed", status)
        self.assertIn("authenticated", status)

    def test_with_repo_injection(self):
        args = self.manager._with_repo(["pr", "list"], "owner/repo")
        self.assertEqual(args[-2:], ["--repo", "owner/repo"])

    def test_set_and_get_default_repo(self):
        self.assertIsNone(self.manager.get_default_repo())
        value = self.manager.set_default_repo("owner/repo")
        self.assertEqual(value, "owner/repo")
        self.assertEqual(self.manager.get_default_repo(), "owner/repo")

    def test_invalid_default_repo_rejected(self):
        with self.assertRaises(ValueError):
            self.manager.set_default_repo("invalid_repo")


if __name__ == "__main__":
    unittest.main()
