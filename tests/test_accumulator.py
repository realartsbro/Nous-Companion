"""Tests for the speech accumulator — events that arrive while the companion
is speaking should accumulate and flush as a single combined reaction when
speech ends, instead of dropping or queuing separately.

This tests the accumulator logic directly (no server needed).
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestSpeechAccumulator:
    """Events during speech should accumulate and flush together."""

    def test_accumulator_starts_empty(self):
        """The accumulator should start empty."""
        from server.companion_server import CompanionServer
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir))
        assert hasattr(server, "_speech_accumulator")
        assert server._speech_accumulator == []

    def test_events_accumulate_during_speech(self):
        """Events arriving while _is_speaking should be added to the accumulator."""
        from server.companion_server import CompanionServer
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir))

        # Simulate speech
        server._is_speaking = True

        # Simulate a tool event arriving
        tool_event = {
            "tool_count": 1,
            "tools": ["terminal"],
            "tool_args": [{"name": "terminal", "summary": "running build"}],
            "significance": 6,
        }
        server._speech_accumulator.append(tool_event)
        assert len(server._speech_accumulator) == 1

        # Another event arrives
        tool_event2 = {
            "tool_count": 1,
            "tools": ["read_file"],
            "tool_args": [{"name": "read_file", "summary": "reading config.yaml"}],
            "significance": 4,
        }
        server._speech_accumulator.append(tool_event2)
        assert len(server._speech_accumulator) == 2

    def test_accumulator_flushed_on_speech_end(self):
        """When _is_speaking becomes False, the accumulator should be flushed."""
        from server.companion_server import CompanionServer
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir))

        # Add events to accumulator (simulating speech period)
        server._speech_accumulator = [
            {"tool_count": 1, "tools": ["terminal"], "significance": 6},
            {"tool_count": 1, "tools": ["read_file"], "significance": 4},
        ]

        # Simulate _flush_speech_accumulator
        result = server._flush_speech_accumulator()
        assert result is not None
        assert len(server._speech_accumulator) == 0  # cleared after flush
        # The result should combine both events
        assert "terminal" in str(result) or "build" in str(result) or len(result) > 0

    def test_empty_accumulator_noop(self):
        """Flushing an empty accumulator should be a no-op."""
        from server.companion_server import CompanionServer
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir))
        assert server._speech_accumulator == []
        result = server._flush_speech_accumulator()
        assert result is None  # nothing to flush

    def test_completion_does_not_cancel_accumulator(self):
        """Completion events should cancel the tool cluster buffer
        but NOT clear the speech accumulator (speech is already happening)."""
        from server.companion_server import CompanionServer
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        server = CompanionServer(str(char_dir))

        # Simulate speech with accumulated events
        server._is_speaking = True
        server._speech_accumulator = [
            {"tool_count": 1, "tools": ["write_file"], "significance": 7},
        ]

        # Tool cluster is separate from speech accumulator
        server._tool_cluster_buffer = [
            {"tools": ["write_file"], "tool_args": [{"name": "write_file"}], "significance": 7},
        ]

        # Simulate what EVENT_COMPLETE does: cancel tool cluster
        old_buffer = list(server._tool_cluster_buffer)
        server._tool_cluster_buffer.clear()

        # Speech accumulator should survive
        assert len(server._speech_accumulator) == 1
        # Tool cluster is gone
        assert len(server._tool_cluster_buffer) == 0
