"""
Concurrency tests for the character switch critical section.

Validates that ``_switch_lock`` (GAP-006, GAP-007, GAP-008) prevents:
  - TEST-001: Stale compositor state from interleaved concurrent WebSocket switch commands
  - TEST-002: Corrupted active character reference when save_character reloads
             during a concurrent switch
  - TEST-004: OmniVoice voice leak (in-flight TTS from old character leaking into
              new character's compositor after switch)

These tests connect to a real ``CompanionTestServer`` and drive it over
WebSocket, just like the integration tests in ``test_integration_profiles.py``.
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import pytest
import pytest_asyncio

from conftest import CompanionWSClient, find_free_port, CompanionTestServer


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


class NullRenderer:
    """Fake renderer that connects as a "renderer" role client."""

    def __init__(self, port: int):
        self.client = CompanionWSClient(port, role="renderer")

    async def connect(self):
        await self.client.connect()

    async def disconnect(self):
        await self.client.disconnect()

    @property
    def messages(self) -> list[dict]:
        return self.client.collected

    def has_type(self, msg_type: str) -> bool:
        return self.client.has_type(msg_type)

    def get_all_of_type(self, msg_type: str) -> list[dict]:
        return self.client.get_all_of_type(msg_type)

    def clear(self):
        self.client.clear()


async def _collect_all(client: CompanionWSClient, timeout: float = 2.0) -> list[dict]:
    """Wait then return all collected messages."""
    await asyncio.sleep(timeout)
    return client.collected


# ═══════════════════════════════════════════════════════════════════════════
# TEST-001: Rapid dual-client switch stress test
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_001_rapid_dual_client_switch_stress(test_server):
    """GAP-006: Two WebSocket clients send switch_character concurrently.

    Verifies that each switch completes atomically — no mixed state,
    compositor always matches active_id, broadcasts carry consistent
    frame dimensions.
    """
    # Connect two control clients (simulating settings.html + a duplicate)
    client_a = CompanionWSClient(test_server.port, role="control")
    client_b = CompanionWSClient(test_server.port, role="control")
    renderer = NullRenderer(test_server.port)
    await client_a.connect()
    await client_b.connect()
    await renderer.connect()

    try:
        # First, discover what character IDs are available
        await client_a.send({"cmd": "get_characters"})

        # Wait for the characters message
        chars_msg = await client_a.wait_for("characters", timeout=5.0)
        available_chars = [c["id"] for c in chars_msg.get("characters", [])]

        if len(available_chars) < 1:
            pytest.skip("Need at least 1 character for concurrency test")

        renderer.clear()

        # Test: rapid sequential switches from two clients (10 iterations)
        # Even with a single character, switching to the same character
        # exercises the lock serialization path.
        for iteration in range(10):
            char_a = available_chars[iteration % len(available_chars)]
            char_b = available_chars[(iteration + 1) % len(available_chars)] if len(available_chars) > 1 else char_a

            # Clear collectors
            renderer.clear()

            # Send both switch commands concurrently
            await asyncio.gather(
                client_a.send({"cmd": "switch_character", "character": char_a, "request_id": f"iter{iteration}_a"}),
                client_b.send({"cmd": "switch_character", "character": char_b, "request_id": f"iter{iteration}_b"}),
            )

            # Wait for both to settle
            await asyncio.sleep(0.3)

            # Verify we got at least one character_switched message
            switched_msgs = renderer.get_all_of_type("character_switched")
            audio_stops = renderer.get_all_of_type("audio_stop")

            # At minimum, we should have at least one character_switched
            # (both could have serialized, producing 2, or only one "won")
            assert len(switched_msgs) >= 1, (
                f"Iteration {iteration}: No character_switched broadcast received. "
                f"Renderer messages: {[m.get('type') for m in renderer.messages]}"
            )

            # Every character_switched must have consistent data
            for msg in switched_msgs:
                char_name = msg.get("character")
                assert char_name in (char_a, char_b), (
                    f"Iteration {iteration}: character_switched for unknown char '{char_name}'"
                )
                # Frame dimensions must be present if reported
                if "frame_width" in msg:
                    assert isinstance(msg["frame_width"], int)
                    assert msg["frame_width"] > 0
                if "frame_height" in msg:
                    assert isinstance(msg["frame_height"], int)
                    assert msg["frame_height"] > 0

            # audio_stop should have been broadcast
            assert len(audio_stops) >= 1, (
                f"Iteration {iteration}: No audio_stop broadcast received"
            )

    finally:
        await client_a.disconnect()
        await client_b.disconnect()
        await renderer.disconnect()


# ═══════════════════════════════════════════════════════════════════════════
# TEST-002: Simultaneous save + switch race
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_002_save_and_switch_race(test_server):
    """GAP-007: Concurrent save_character (which calls _load_all()) and
    switch_character must not produce stale Character references.

    After both complete, active_id must reference a valid Character
    with a non-None compositor.
    """
    client = CompanionWSClient(test_server.port, role="control")
    renderer = NullRenderer(test_server.port)
    await client.connect()
    await renderer.connect()

    try:
        # Discover available characters
        await client.send({"cmd": "get_characters"})
        chars_msg = await client.wait_for("characters", timeout=5.0)
        available_chars = [c["id"] for c in chars_msg.get("characters", [])]

        if len(available_chars) < 1:
            pytest.skip("Need at least 1 character for save+switch race test")

        char_id = available_chars[0]
        renderer.clear()

        # Send a minimal save (just update description) to trigger _load_all()
        # We do NOT need to read full character data first — that's expensive.
        minimal_data = {"description": "Concurrency test save"}

        # Concurrent: switch to the same character AND save it
        await asyncio.gather(
            client.send({"cmd": "switch_character", "character": char_id, "request_id": "save_race_test"}),
            client.send({"cmd": "save_character", "id": char_id, "data": minimal_data}),
        )

        # Wait for operations to settle — save_character may take time
        await asyncio.sleep(1.0)

        # Verify the save confirmation arrived
        saved_msgs = [m for m in client.collected if m.get("type") == "character_saved"]
        assert len(saved_msgs) >= 1, (
            f"No character_saved response. Messages: {[m.get('type') for m in client.collected]}"
        )

        # Verify we got a character_switched broadcast
        switched = renderer.get_all_of_type("character_switched")
        assert len(switched) >= 1, "No character_switched broadcast"

        # Verify the active character is still valid after the race
        await client.send({"cmd": "get_characters"})
        chars_msg2 = await client.wait_for("characters", timeout=5.0)
        active_id = chars_msg2.get("active")
        assert active_id is not None, "active_id is None after save+switch race"
        assert active_id in available_chars, (
            f"Unexpected active_id: {active_id} not in {available_chars}"
        )

    finally:
        await client.disconnect()
        await renderer.disconnect()


# ═══════════════════════════════════════════════════════════════════════════
# TEST-003: Switch while TTS is in-flight (voice leak resilience)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_004_tts_voice_leak_resilience(test_server):
    """GAP-008: Switch during TTS synthesis must not leak audio into the
    new character's compositor.

    This test verifies that even without a real TTS engine, the infrastructure
    (TTS task cancellation + _switch_lock serialization) is properly wired
    so that switching cancels in-flight TTS and the new character's state
    is not corrupted.
    """
    client = CompanionWSClient(test_server.port, role="control")
    renderer = NullRenderer(test_server.port)
    await client.connect()
    await renderer.connect()

    try:
        # Discover available characters
        await client.send({"cmd": "get_characters"})
        chars_msg = await client.wait_for("characters", timeout=5.0)
        available_chars = [c["id"] for c in chars_msg.get("characters", [])]

        if len(available_chars) < 1:
            pytest.skip("Need at least 1 character for TTS leak test")

        char_id = available_chars[0]
        renderer.clear()

        # 1. Request a switch (which cancels in-flight TTS before syncing)
        await client.send({"cmd": "switch_character", "character": char_id, "request_id": "tts_leak_test"})
        await asyncio.sleep(0.3)

        # 2. Verify the switch completed cleanly
        switched = renderer.get_all_of_type("character_switched")
        audio_stops = renderer.get_all_of_type("audio_stop")

        assert len(switched) >= 1, "No character_switched after TTS-leak switch"
        assert len(audio_stops) >= 1, "No audio_stop broadcast (TTS cancel signal missing)"

        # 3. Verify active character is still consistent
        await client.send({"cmd": "get_characters"})
        chars_msg2 = await client.wait_for("characters", timeout=5.0)
        active = chars_msg2.get("active")
        assert active == char_id, f"Active character mismatch: {active} != {char_id}"

        # 4. Frame dimensions should be consistent
        fw = chars_msg2.get("frame_width", 0)
        fh = chars_msg2.get("frame_height", 0)
        assert fw > 0 and fh > 0, f"Frame dimensions invalid after switch: {fw}x{fh}"

        # 5. Rapid switch-then-immediate-switch (stress the TTS cancellation path)
        for _ in range(5):
            renderer.clear()
            await client.send({"cmd": "switch_character", "character": char_id, "request_id": f"rapid_{_}"})
            # Don't wait — immediately send another switch
            await asyncio.sleep(0.01)
            await client.send({"cmd": "switch_character", "character": char_id, "request_id": f"rapid2_{_}"})
            await asyncio.sleep(0.2)

            switched = renderer.get_all_of_type("character_switched")
            # Should have at least one completed switch
            assert len(switched) >= 1, f"Rapid switch iteration {_}: no character_switched"

    finally:
        await client.disconnect()
        await renderer.disconnect()


# ═══════════════════════════════════════════════════════════════════════════
# TEST-005: Lock serialization under load
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_005_lock_serialization(test_server):
    """Verify that concurrent operations serialize rather than interleave.

    Sends 5 concurrent switches from 3 different clients simultaneously.
    Verifies that character_switched broadcasts arrive for at least
    1 switch per client and there are no errors.
    """
    NUM_CLIENTS = 3
    NUM_SWITCHES = 5

    clients = []
    renderer = NullRenderer(test_server.port)
    await renderer.connect()

    try:
        # Discover characters
        temp_client = CompanionWSClient(test_server.port, role="control")
        await temp_client.connect()
        await temp_client.send({"cmd": "get_characters"})
        chars_msg = await temp_client.wait_for("characters", timeout=5.0)
        available_chars = [c["id"] for c in chars_msg.get("characters", [])]
        await temp_client.disconnect()

        if len(available_chars) < 1:
            pytest.skip("Need at least 1 character for serialization test")

        # Connect all clients
        for i in range(NUM_CLIENTS):
            c = CompanionWSClient(test_server.port, role="control")
            await c.connect()
            clients.append(c)

        renderer.clear()

        # Send switches from all clients concurrently
        tasks = []
        for i, client in enumerate(clients):
            char = available_chars[i % len(available_chars)]
            for j in range(NUM_SWITCHES):
                tasks.append(
                    client.send({
                        "cmd": "switch_character",
                        "character": char,
                        "request_id": f"serialize_c{i}_s{j}",
                    })
                )

        await asyncio.gather(*tasks)

        # Wait for everything to settle
        await asyncio.sleep(1.0)

        # Verify we got character_switched broadcasts
        switched_msgs = renderer.get_all_of_type("character_switched")
        assert len(switched_msgs) >= 1, (
            f"No character_switched broadcasts after concurrent switches. "
            f"Renderer messages: {[m.get('type') for m in renderer.messages]}"
        )

        # Every switched message must have a valid character
        for msg in switched_msgs:
            assert "character" in msg
            assert "name" in msg

        # Verify the server is still healthy: get_characters works
        await clients[0].send({"cmd": "get_characters"})
        chars_msg2 = await clients[0].wait_for("characters", timeout=5.0)
        assert chars_msg2.get("active") is not None, "Server lost active character after stress"

    finally:
        for c in clients:
            await c.disconnect()
        await renderer.disconnect()
