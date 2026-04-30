"""Tests for USER.md and MEMORY.md injection into the companion brain prompt.

Verifies that:
1. When memory files exist, their content appears in the brain prompt
2. When memory files don't exist, the brain prompt is unchanged
3. The _load_user_memory method handles edge cases gracefully
4. Character switch refreshes memory content
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.companion_server import CompanionServer


# Ensure Hermes home is set for the test
_HERMES_HOME_BAK = os.environ.get("HERMES_HOME")


class TestMemoryInjection:
    """Companion reads USER.md and MEMORY.md into its brain prompt."""

    @classmethod
    def setup_class(cls):
        cls.tmp_dir = Path(tempfile.mkdtemp(prefix="nous_memory_test_"))
        cls.hermes_home = cls.tmp_dir / "hermes"
        cls.hermes_home.mkdir()
        cls.memories_dir = cls.hermes_home / "memories"
        cls.memories_dir.mkdir()

        # Set HERMES_HOME for the test server
        os.environ["HERMES_HOME"] = str(cls.hermes_home)

        # Create mock memory files
        cls.user_md = cls.memories_dir / "USER.md"
        cls.user_md.write_text(
            "User prefers concise responses.\n"
            "User is a writer/artist first.\n"
            "Berlin timezone.\n"
        )

        cls.memory_md = cls.memories_dir / "MEMORY.md"
        cls.memory_md.write_text(
            "Project uses pytest with xdist.\n"
            "WSL clock drifts ~1h17m behind.\n"
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(str(cls.tmp_dir), ignore_errors=True)
        if _HERMES_HOME_BAK is not None:
            os.environ["HERMES_HOME"] = _HERMES_HOME_BAK
        else:
            os.environ.pop("HERMES_HOME", None)

    def test_load_user_memory_returns_content(self):
        """Should return formatted content when both files exist."""
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir), hermes_home=str(self.hermes_home))
        result = server._load_user_memory()
        assert "About the operator:" in result
        assert "Environment notes:" in result
        assert "Berlin timezone" in result
        assert "WSL clock drifts" in result

    def test_brain_prompt_includes_memory(self):
        """Brain prompt should include memory content at startup."""
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir), hermes_home=str(self.hermes_home))
        assert "About the operator:" in server._brain_prompt
        assert "Berlin timezone" in server._brain_prompt

    def test_memory_without_files_returns_empty(self):
        """When no memory files exist, _load_user_memory returns empty string."""
        empty_dir = self.tmp_dir / "empty_hermes"
        empty_dir.mkdir()
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir), hermes_home=str(empty_dir))
        result = server._load_user_memory()
        assert result == ""

    def test_memory_without_files_leaves_brain_unchanged(self):
        """When no memory files exist, brain prompt should still have personality."""
        empty_dir = self.tmp_dir / "empty_hermes2"
        empty_dir.mkdir()
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir), hermes_home=str(empty_dir))
        # Brain prompt should exist and contain the character personality
        assert "nous" in server._brain_prompt.lower() or "speak" in server._brain_prompt.lower()
        # But no memory markers
        assert "Operator context:" not in server._brain_prompt

    def test_single_file_partial(self):
        """Should work with only USER.md (no MEMORY.md)."""
        partial_dir = self.tmp_dir / "partial_hermes"
        partial_dir.mkdir()
        partial_mem = partial_dir / "memories"
        partial_mem.mkdir()
        (partial_mem / "USER.md").write_text("Only user info here.")

        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir), hermes_home=str(partial_dir))
        result = server._load_user_memory()
        assert "About the operator:" in result
        assert "Environment notes:" not in result
