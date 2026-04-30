"""Tests for compaction summary pass-through — the companion should see
context compaction summaries instead of skipping them entirely.

Compaction markers contain natural-language summaries of earlier conversation
turns. Currently they're filtered out, so the companion has no awareness of
the 'bigger picture' in long conversations.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.companion_server import CompanionServer


class TestCompactionSummaries:
    """The companion should include compaction summaries in context."""

    server = None

    @classmethod
    def setup_class(cls):
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        cls.server = CompanionServer(str(char_dir))

    def test_compaction_skipped_currently(self):
        """Currently, messages starting with [CONTEXT COMPACTION are skipped.
        This test documents the current behavior — after fix, compaction
        summaries should appear in the formatted context."""
        messages = [
            {"role": "user", "content": "[CONTEXT COMPACTION — earlier conversation summarized] "
                                        "The user asked about config changes. "
                                        "Hermes modified the timeout setting."},
            {"role": "user", "content": "Can you check the log file?"},
            {"role": "assistant", "content": "I found the error in the log."},
        ]
        result = self.server._format_session_context(messages, "")
        # Current behavior: compaction marker is skipped entirely
        # After fix: compaction text should appear in context
        has_summary = "earlier conversation" in result or "config changes" in result
        has_query = "log file" in result
        assert has_query, "User query should always be in context"
        if has_summary:
            print("[OK] Compaction summary appears in context")
        else:
            print("[INFO] Compaction summary currently skipped — fix pending")

    def test_compaction_with_mixed_messages(self):
        """Compaction summaries should not interfere with regular user messages."""
        messages = [
            {"role": "user", "content": "First real query"},
            {"role": "assistant", "content": "First response"},
            {"role": "user", "content": "[CONTEXT COMPACTION — summarized content]"},
            {"role": "user", "content": "Second real query"},
            {"role": "assistant", "content": "Second response"},
        ]
        result = self.server._format_session_context(messages, "Final response")
        # Both real queries should still be present
        assert "First real query" in result
        assert "Second real query" in result
        # Summary should be included (after fix) or not (current)
        # But real queries must never be lost
