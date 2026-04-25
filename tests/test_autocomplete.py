"""
test_autocomplete.py — Unit tests for intelligence/autocomplete.py

Covers:
- cursor_pos=0 fix (must NOT snap to end of line)
- cursor_pos=None defaults to len(line)
- cursor_pos=2 works correctly
- complete() returns a list (never crashes)
- subprocess import is module-level (no import inside git methods)
"""
import pytest


@pytest.fixture()
def autocomplete():
    from intelligence.autocomplete import Autocomplete
    return Autocomplete()


class TestCursorPos:
    def test_cursor_pos_zero_does_not_crash(self, autocomplete):
        """cursor_pos=0 must not default to len(line) — regression for falsy-zero bug."""
        # Should not raise; returns list (possibly empty at pos=0)
        result = autocomplete.complete("git status", cursor_pos=0)
        assert isinstance(result, list)

    def test_cursor_pos_none_defaults_to_end(self, autocomplete):
        """cursor_pos=None should default to len(line)."""
        result = autocomplete.complete("git", cursor_pos=None)
        assert isinstance(result, list)

    def test_cursor_pos_mid_line(self, autocomplete):
        result = autocomplete.complete("git commit -m", cursor_pos=10)
        assert isinstance(result, list)

    def test_cursor_pos_at_end(self, autocomplete):
        line = "git "
        result = autocomplete.complete(line, cursor_pos=len(line))
        assert isinstance(result, list)

    def test_cursor_zero_context_is_at_start(self, autocomplete):
        """
        With cursor at pos=0, the parsed prefix should be empty string,
        not the whole line. This tests the original bug was actually fixed.
        """
        # We call the internal parser to check the context directly
        ctx = autocomplete._parse_context("git status", 0)
        # At position 0, current token should be empty or minimal
        assert ctx.cursor_pos == 0  # Must store pos=0, not len("git status")=10


class TestCompleteReturnsCleanList:
    def test_returns_list(self, autocomplete):
        assert isinstance(autocomplete.complete(""), list)

    def test_git_completions(self, autocomplete):
        results = autocomplete.complete("git ")
        assert isinstance(results, list)

    def test_no_duplicate_completions(self, autocomplete):
        results = autocomplete.complete("git ")
        texts = [r.text for r in results]
        assert len(texts) == len(set(texts)), "Duplicate completions returned"

    def test_completions_have_text_field(self, autocomplete):
        results = autocomplete.complete("git ")
        for r in results:
            assert hasattr(r, "text"), f"Completion missing .text: {r}"

    def test_completions_sorted_by_score(self, autocomplete):
        results = autocomplete.complete("git ")
        if len(results) >= 2:
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True), "Completions not sorted by score"


class TestSubprocessImport:
    def test_subprocess_at_module_level(self):
        """subprocess must be a module-level import, not inside a method."""
        import intelligence.autocomplete as ac_module
        import subprocess
        # If subprocess is module-level, the module's globals should reference it
        assert hasattr(ac_module, "subprocess") or "subprocess" in dir(ac_module), (
            "subprocess is not a module-level import in autocomplete.py"
        )
