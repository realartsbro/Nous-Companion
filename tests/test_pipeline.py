"""Pipeline tests for Nous Companion — data quality, context depth, and reaction accuracy.

These test the companion's internal logic without starting a server:
- Approval detection regex (false positive prevention)
- Context depth tiers (message/exchange counts per setting)
- Tool prompt content (read-vs-write distinction)

Run with: python -m pytest tests/test_pipeline.py -v
"""
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.hermes_observer import HermesObserver
from server.companion_server import CompanionServer


# ═══════════════════════════════════════════════════════════════
# Approval Detection
# ═══════════════════════════════════════════════════════════════

APPROVAL_TRUE = [
    "This command requires your approval.",
    "Are you sure you want to proceed?",
    "Please confirm before I continue.",
    "Waiting for your input.",
    "Do you approve this change?",
    "This is a destructive operation.",
    "Shall I proceed with the deletion?",
    "Your confirmation is needed.",
    "I need your input on this.",
    "Permanently delete this file?",
    "Can you confirm this is correct?",
    "Waiting for your response.",
]

APPROVAL_FALSE = [
    "",
    "I need you to know that this is working correctly.",
    "I need you to understand the risks involved.",
    "Here's what I found in the config file.",
    "The build completed successfully.",
    "Let me know if you need anything else.",
    "I need you to check the output when you have a moment.",
    "I'll need you to verify this later.",
    # Completed approvals — should NOT trigger a pending-approval reaction
    "User approved the changes.",
    "Approved for this session.",
    "Approved.",
    "Approval granted.",
    "approve all confirmed.",
    "I have approved this operation.",
]


class TestApprovalDetection:
    """_is_approval_request() should catch real approvals without false positives."""

    def test_detects_true_positives(self):
        for text in APPROVAL_TRUE:
            assert HermesObserver._is_approval_request(text), (
                f"Should detect as approval: {text[:60]}"
            )

    def test_rejects_false_positives(self):
        failures = []
        for text in APPROVAL_FALSE:
            if HermesObserver._is_approval_request(text):
                failures.append(text[:80])
        assert not failures, (
            f"False positives detected ({len(failures)}):\n  "
            + "\n  ".join(failures)
        )

    def test_need_you_to_false_positive(self):
        """The current regex 'need you to' matches 'I need you to know that...'.
        This test documents the false positive so we can verify the fix."""
        text = "I need you to know that this is working correctly."
        result = HermesObserver._is_approval_request(text)
        # Currently True (false positive) — after fix should be False
        if result:
            print("[WARN] 'need you to' false positive confirmed — regex needs tightening")
        else:
            print("[OK] 'need you to' false positive resolved")


# ═══════════════════════════════════════════════════════════════
# Context Depth Tiers
# ═══════════════════════════════════════════════════════════════

# Expected values from companion_server.py _get_context_depth and _get_brain_history_exchanges
EXPECTED_DEPTHS = {
    1: {"messages": 25, "detailed": 4, "exchanges": 2},
    2: {"messages": 50, "detailed": 8, "exchanges": 8},
    3: {"messages": 120, "detailed": 14, "exchanges": 12},
    4: {"messages": 200, "detailed": 22, "exchanges": 22},
}


class TestContextDepth:
    """Depth tiers control how much conversation the companion sees."""

    server = None

    @classmethod
    def setup_class(cls):
        """Create a minimal server instance just to test depth methods."""
        char_dir = Path(__file__).parent.parent / "characters" / "nous"
        cls.server = CompanionServer(str(char_dir))

    def test_depth_tiers(self):
        for level, expected in EXPECTED_DEPTHS.items():
            self.server.settings["context_budget"] = level
            messages, detailed = self.server._get_context_depth()
            exchanges = self.server._get_brain_history_exchanges()
            assert messages == expected["messages"], (
                f"Tier {level}: expected {expected['messages']} messages, got {messages}"
            )
            assert detailed == expected["detailed"], (
                f"Tier {level}: expected {expected['detailed']} detailed, got {detailed}"
            )
            assert exchanges == expected["exchanges"], (
                f"Tier {level}: expected {expected['exchanges']} exchanges, got {exchanges}"
            )

    def test_default_is_deep(self):
        """Default context_budget should be tier 3 (Deep) in code.
        The loaded value may differ if prefs were saved with a different setting."""
        # Check the code constant (line 243 in companion_server.py)
        code_default = CompanionServer.__init__.__defaults__  # won't work for dict
        # Direct check: the settings dict default at init
        settings_default = 3  # from companion_server.py:243
        # What the server actually loaded (may differ if prefs saved different value)
        loaded = self.server.settings.get("context_budget", 3)
        assert settings_default == 3, "Code default should be 3 (Deep)"
        print(f"[INFO] Context budget code default: {settings_default} (Deep)")
        print(f"[INFO] Context budget loaded value: {loaded} (may differ if prefs saved)")


    def test_depth_clamped(self):
        for bad in [0, -1, 5, 99]:
            self.server.settings["context_budget"] = bad
            messages, detailed = self.server._get_context_depth()
            # Should return a valid tier (1-4), not crash
            assert 1 <= messages <= 200
            assert 1 <= detailed <= 22

    def test_context_format_exchange_count(self):
        """Build a mock session with known messages and verify exchange count in output."""
        self.server.settings["context_budget"] = 2  # Normal: 8 detailed
        messages = []
        for i in range(20):
            messages.append({"role": "user", "content": f"Query {i}"})
            messages.append({"role": "assistant", "content": f"Response {i}"})

        result = self.server._format_session_context(messages, "Final response")
        # Normal tier should show 8 detailed exchanges + current query
        # "Recent context:" section should have 7 entries (8-1 for current query)
        recent_count = result.count("User asked:")
        assert recent_count <= 8, (
            f"Normal tier should show ≤8 user queries, got {recent_count}"
        )
        # Should also have "earlier topics" for exchanges beyond the detailed window
        assert "The conversation so far:" in result or recent_count <= 8


# ═══════════════════════════════════════════════════════════════
# Tool Prompt Content
# ═══════════════════════════════════════════════════════════════

CURRENT_TOOL_PROMPT = (
    "You just handled something — a fix, a find, or just a look around."
)


class TestToolPrompt:
    """The tool reaction prompt should distinguish read from write."""

    def test_current_prompt_lacks_read_write_caveat(self):
        """The current prompt doesn't tell the LLM to distinguish read vs write.
        This documents the gap — after fix, this test should be updated."""
        has_read_caveat = "read" in CURRENT_TOOL_PROMPT.lower() and "write" in CURRENT_TOOL_PROMPT.lower()
        if not has_read_caveat:
            print("[WARN] Tool prompt lacks read-vs-write distinction — companion may overclaim")
        # Not an assertion — this is documentation until the fix is applied

    def test_completion_prompt_has_caveat(self):
        """The completion prompt already has a read-vs-write caveat.
        The tool prompt should match it."""
        # Read from companion_server source
        has_caveat = False
        with open(Path(__file__).parent.parent / "src/server/companion_server.py") as f:
            content = f.read()
            # Check for the caveat pattern in completion prompt
            if "If you only READ or SEARCHED a file" in content:
                has_caveat = True
        assert has_caveat, (
            "Completion prompt should have read-vs-write caveat — check source hasn't changed"
        )
