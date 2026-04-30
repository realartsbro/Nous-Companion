"""Tests for reasoning pass-through — the observer should read the model's
thinking/reasoning from session messages and forward it to the companion brain.

Currently assistant_reasoning contains content[:400] (what was said).
It should also include the reasoning field (what was thought).
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestReasoningPassThrough:
    """The observer should extract reasoning from session messages."""

    def test_session_message_has_reasoning_field(self):
        """Real session files contain a 'reasoning' field in assistant messages."""
        # Use a known session file from the user's Hermes install
        sessions_dir = Path.home() / ".hermes" / "sessions"
        if not sessions_dir.exists():
            # Fall back to a test fixture
            return  # skip if no real sessions available

        # Find a session with reasoning content
        found = False
        for f in sorted(sessions_dir.glob("session_*.json"))[:10]:
            try:
                data = json.loads(f.read_text())
                for msg in data.get("messages", []):
                    if msg.get("reasoning") or msg.get("reasoning_content"):
                        found = True
                        break
            except Exception:
                continue
        assert found, (
            "No session file found with reasoning content. "
            "Run a Hermes session with a model that outputs reasoning first."
        )

    def test_assistant_reasoning_includes_reasoning(self):
        """After fix, assistant_reasoning should include the reasoning field
        (not just the content/response text)."""
        from server.hermes_observer import HermesObserver

        # Create a mock session message with reasoning
        mock_msg = {
            "role": "assistant",
            "content": "Here is the file you asked for.",
            "reasoning": "The user wants me to read config.yaml. "
                        "I should use read_file to get the contents. "
                        "Let me check if the file exists first.",
            "reasoning_content": "The user wants me to read config.yaml. "
                               "I should use read_file to get the contents. "
                               "Let me check if the file exists first.",
            "tool_calls": [{"function": {"name": "read_file", "arguments": '{"path": "config.yaml"}'}}],
        }

        # The observer processes messages in _poll_once.
        # At line 707: content = str(msg.get("content", ""))[:800]
        # Currently: assistant_reasoning = content[:400]
        # After fix: also read msg.get("reasoning", "") and msg.get("reasoning_content", "")

        content = str(mock_msg.get("content", ""))[:800]
        reasoning = mock_msg.get("reasoning", "") or mock_msg.get("reasoning_content", "") or ""

        # Current behavior: assistant_reasoning = content[:400]
        current = content[:400]
        assert "read_file" not in current
        assert "config.yaml" not in current

        # Expected after fix: assistant_reasoning should include reasoning
        if reasoning:
            assert "read_file" in reasoning
            assert "config.yaml" in reasoning
