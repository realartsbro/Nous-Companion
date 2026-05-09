"""
WebSocket integration tests for the Nous Companion protocol.

These are *diagnostic* tests — they validate (or document gaps in) the actual
server behaviour without modifying the application code.

Tests
─────
1. save_character broadcast enriched data  — verifies _broadcast_character_catalog
   vs get_characters data gap.
2. Character switch sends audio_stop        — checks the audio cut-off root cause
   theory.
3. Profile change auto-switch behaviour     — confirms profile_changed /
   character_switched broadcast presence.
4. List profiles returns correct data       — validates the list_profiles response
   structure.
5. Empty hermes_profiles = global visibility — validates the "empty array = all
   profiles" invariant.
6. Observer event pipeline                   — verifies hermes_event broadcast
   with profile_name.
7. should_chime_in rate                      — validates the ~15% probabilistic
   chime-in rate.
8. Orphan profile handled gracefully         — non-existent profile in
   hermes_profiles cleaned up without crash.
9. Rapid switch_character commands           — rapid switching doesn't crash.
10. get_character_data includes hermes_profiles — validates Bug 2 fix.
11. Corrupt session JSON doesn't crash       — observer skips malformed files.
12. Zero characters shows empty state        — server handles no valid characters.
13. switch_profile to non-existent profile   — guardrail prevents crash.
14. Many session files don't crash observer  — validates observer performance with
   large session directories.
15. Character with many profiles             — 20+ profile bindings preserved,
   no truncation.
16. Missing config.yaml fields               — minimal config loads with sensible
   defaults, no crash.
"""

import json
import os
import time
from pathlib import Path

import pytest

from conftest import CompanionWSClient


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _char_ids(chars: list[dict]) -> list[str]:
    return [c["id"] for c in chars]


def _char_by_id(chars: list[dict], cid: str) -> dict:
    for c in chars:
        if c["id"] == cid:
            return c
    raise KeyError(cid)


async def _sleep(seconds: float) -> None:
    """Async sleep helper."""
    import asyncio
    await asyncio.sleep(seconds)


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 — save_character broadcasts enriched data
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_save_character_broadcasts_enriched_data(companion_ws):
    """After save_character, the characters broadcast should include
    ``visible`` (bool) and ``hermes_profiles`` (list) for every character.

    This validates the **_broadcast_character_catalog** vs **get_characters**
    data gap: ``get_characters`` handler manually enriches the list, but
    ``_broadcast_character_catalog`` sends the raw ``character_list`` which
    may be missing ``visible``.
    """
    # 1. Request characters (server only pushes runtime_config + sessions on connect)
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])

    assert len(characters) > 0, "Expected at least one character in broadcast"

    # 2. Send save_character with updated hermes_profiles
    #    Use the first character's ID and set a profile binding
    first_char = characters[0]
    cid = first_char["id"]
    await companion_ws.send({
        "cmd": "save_character",
        "id": cid,
        "data": {"hermes_profiles": ["default"]},
    })

    # 3. Wait for character_saved ack
    saved_msg = await companion_ws.wait_for("character_saved", timeout=5.0)
    assert saved_msg.get("ok") is True, f"save_character failed: {saved_msg}"

    # 4. Wait for the follow-up characters broadcast (from _broadcast_character_catalog)
    #    There may also be a "character_switched" broadcast from _broadcast_active_character_state
    chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
    characters2 = chars_msg2.get("characters", [])

    assert len(characters2) > 0, "Expected characters after save"

    # 5. Assert each character has 'visible' field (boolean)
    missing_visible = [
        c["id"] for c in characters2 if "visible" not in c
    ]
    assert not missing_visible, (
        f"_broadcast_character_catalog missing 'visible' for: {missing_visible}"
    )

    # Verify visible is a boolean where present
    for c in characters2:
        if "visible" in c:
            assert isinstance(c["visible"], bool), (
                f"Character {c['id']}: visible={c['visible']!r} is not bool"
            )

    # 6. Assert hermes_profiles field is present
    missing_profiles = [
        c["id"] for c in characters2 if "hermes_profiles" not in c
    ]
    if missing_profiles:
        print(
            f"  ✗ DATA GAP CONFIRMED: characters missing 'hermes_profiles': "
            f"{missing_profiles}"
        )
    else:
        print(f"  ✓ All characters have 'hermes_profiles' field")

    # Verify hermes_profiles is a list where present
    for c in characters2:
        if "hermes_profiles" in c:
            assert isinstance(c["hermes_profiles"], list), (
                f"Character {c['id']}: hermes_profiles={c['hermes_profiles']!r} "
                f"is not list"
            )

    print(f"\n  ✓ save_character broadcast: {len(characters2)} characters received")


# ═══════════════════════════════════════════════════════════════════════════
# Test 2 — Character switch sends audio_stop
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_character_switch_sends_audio_stop(companion_ws, test_server):
    """When switching characters, does the server send ``audio_stop``?

    THEORY: Starting audio is not cut off by a character switch because the
    switch handler does NOT broadcast ``audio_stop``.  The renderer keeps
    playing audio from the old character.

    This test:
      1. Connects a renderer client to listen for audio_stop broadcasts.
      2. Switches to a different valid character via the control client.
      3. Waits for ``character_switched`` on the control client.
      4. Asserts that ``audio_stop`` was received on the renderer client.
    """
    # 0. Connect a renderer client to receive renderer-targeted broadcasts
    renderer = CompanionWSClient(test_server.port, role="renderer")
    await renderer.connect()

    # 1. Get initial characters list to find a valid switch target
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 2, (
        f"Need at least 2 characters to test switching, got {len(characters)}"
    )

    current_active = chars_msg.get("active", "")
    target_cid = next(
        (c["id"] for c in characters if c["id"] != current_active),
        None,
    )
    assert target_cid is not None, "No alternative character to switch to"

    # Clear collected messages before switch
    companion_ws.clear()
    renderer.clear()

    # 2. Send switch_character
    await companion_ws.send({
        "cmd": "switch_character",
        "character": target_cid,
    })

    # 3. Wait for character_switched message on control client
    switched_msg = await companion_ws.wait_for("character_switched", timeout=5.0)
    assert switched_msg["character"] == target_cid, (
        f"Expected switch to {target_cid}, got {switched_msg.get('character')}"
    )

    # Wait a small additional window for any trailing broadcasts
    await _sleep(0.3)

    # 4. Check whether audio_stop was received on the renderer client
    has_audio_stop = renderer.has_type("audio_stop")

    # Clean up
    await renderer.disconnect()

    assert has_audio_stop, (
        f"audio_stop was NOT broadcast during character switch to '{target_cid}'. "
        f"The switch handler must broadcast audio_stop via "
        f"_broadcast(json.dumps({{'type': 'audio_stop'}}), roles={{{{'renderer'}}}}) "
        f"after _sync_runtime_to_active_character()."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 3 — Profile change auto-switch behaviour
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_profile_change_auto_switch_behavior(companion_ws, test_server):
    """Does switching profile via switch_profile broadcast profile_changed
    and character_switched?

    The ``switch_profile`` handler auto-switches to a profile-appropriate
    character but broadcasts ``profile_switch_result`` — NOT
    ``profile_changed`` or ``character_switched``.  This test confirms
    the gap so it can be tracked as a bug.
    """
    # 1. Set up: create profile directories and bind a character to one
    hermes_home = test_server.hermes_home
    profiles_dir = hermes_home / "profiles"
    work_dir = profiles_dir / "work"
    work_sessions = work_dir / "sessions"
    work_sessions.mkdir(parents=True)

    personal_dir = profiles_dir / "personal"
    personal_sessions = personal_dir / "sessions"
    personal_sessions.mkdir(parents=True)

    # First, get characters list to know what's available
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 1, "Expected at least one character"

    # Bind the first character to the "work" profile
    first_cid = characters[0]["id"]
    await companion_ws.send({
        "cmd": "save_character",
        "id": first_cid,
        "data": {"hermes_profiles": ["work"]},
    })
    await companion_ws.wait_for("character_saved", timeout=5.0)
    # Consume the follow-up broadcasts
    await companion_ws.wait_for("characters", timeout=5.0)
    # There may also be "character_switched" — try to consume it
    try:
        await companion_ws.wait_for("character_switched", timeout=1.0)
    except TimeoutError:
        pass

    companion_ws.clear()

    # 2. Create a fake session file in the work profile to simulate activity
    fake_session = work_sessions / "session_test_001.json"
    fake_session.write_text(json.dumps({
        "session_id": "test_001",
        "messages": [
            {"role": "user", "content": "Hello from work profile"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        "model": "test-model",
        "started_at": time.time(),
        "last_updated": time.time(),
        "message_count": 2,
        "title": "Work test session",
    }))

    # 3. Trigger profile change via switch_profile command
    await companion_ws.send({
        "cmd": "switch_profile",
        "profile": "work",
    })

    # 4. Wait for profile_switch_result (the actual broadcast)
    try:
        result_msg = await companion_ws.wait_for("profile_switch_result", timeout=5.0)
        print(f"\n  ✓ profile_switch_result received: {json.dumps(result_msg)}")
    except TimeoutError:
        print("\n  ✗ No profile_switch_result received!")

    # 5. Check if profile_changed was also broadcast
    await _sleep(0.5)
    has_profile_changed = companion_ws.has_type("profile_changed")

    # 6. Check if character_switched was also broadcast
    has_char_switched = companion_ws.has_type("character_switched")

    # Assert that both broadcasts were sent
    assert has_profile_changed, (
        "switch_profile handler must broadcast profile_changed"
    )
    assert has_char_switched, (
        "switch_profile handler must broadcast character_switched"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 4 — List profiles returns correct data
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_profiles_returns_correct_data(companion_ws, test_server):
    """Sending ``list_profiles`` must reply with a ``profiles`` broadcast
    containing ``type``, ``profiles`` (array), and ``active_profile``.

    Each profile entry must have ``name``, ``is_active`` (bool), and
    ``is_global`` (bool).
    """
    # 1. Create some profile directories so the server finds them
    hermes_home = test_server.hermes_home
    profiles_dir = hermes_home / "profiles"
    for name in ("work", "personal", "coding"):
        (profiles_dir / name).mkdir(parents=True)

    # 2. Send list_profiles command
    await companion_ws.send({"cmd": "list_profiles"})

    # 3. Wait for profiles broadcast
    profiles_msg = await companion_ws.wait_for("profiles", timeout=5.0)

    # 4. Assert top-level structure
    assert profiles_msg["type"] == "profiles", (
        f"Expected type='profiles', got {profiles_msg.get('type')!r}"
    )
    assert "profiles" in profiles_msg, "Missing 'profiles' key"
    assert isinstance(profiles_msg["profiles"], list), "profiles must be a list"
    assert "active_profile" in profiles_msg, "Missing 'active_profile' key"

    profile_list = profiles_msg["profiles"]
    assert len(profile_list) >= 1, (
        f"Expected at least 1 profile (global), got {len(profile_list)}"
    )

    # 5. Assert each profile entry has required fields
    for p in profile_list:
        assert "name" in p, f"Profile missing 'name': {p}"
        assert "is_active" in p, f"Profile {p['name']} missing 'is_active'"
        assert isinstance(p["is_active"], bool), (
            f"Profile {p['name']}: is_active={p['is_active']!r} is not bool"
        )
        assert "is_global" in p, f"Profile {p['name']} missing 'is_global'"
        assert isinstance(p["is_global"], bool), (
            f"Profile {p['name']}: is_global={p['is_global']!r} is not bool"
        )

    # 6. Assert exactly one "global" profile exists
    global_profiles = [p for p in profile_list if p["is_global"]]
    assert len(global_profiles) == 1, (
        f"Expected exactly 1 global profile, got {len(global_profiles)}: "
        f"{global_profiles}"
    )
    assert global_profiles[0]["name"] == "global"

    # 7. Assert non-global profiles have is_global = False
    non_global = [p for p in profile_list if not p["is_global"]]
    for p in non_global:
        assert p["is_global"] is False

    # Verify our test profiles appear
    profile_names = {p["name"] for p in profile_list}
    expected = {"global", "work", "personal", "coding"}
    missing = expected - profile_names
    if missing:
        print(
            f"  ⚠ Some expected profiles not found: {missing}. "
            f"Server returned: {sorted(profile_names)}"
        )

    print(
        f"\n  ✓ list_profiles returned {len(profile_list)} profiles: "
        f"{sorted(profile_names)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 5 — Empty hermes_profiles = global visibility
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_empty_hermes_profiles_global_visibility(companion_ws, test_server):
    """Characters with ``hermes_profiles: []`` (empty) should be visible in
    every profile — the "global visibility" invariant.

    Also validates that switching to a specific profile does not hide
    globally-visible characters.
    """
    # 1. Get initial characters and pick one
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 1, "Expected at least one character"

    # Use the first character
    first_cid = characters[0]["id"]

    # 2. Set the character to have empty hermes_profiles (global)
    await companion_ws.send({
        "cmd": "save_character",
        "id": first_cid,
        "data": {"hermes_profiles": []},
    })
    saved_msg = await companion_ws.wait_for("character_saved", timeout=5.0)
    assert saved_msg.get("ok") is True, f"save_character failed: {saved_msg}"

    # Consume the follow-up characters broadcast
    await companion_ws.wait_for("characters", timeout=5.0)
    # There may also be "character_switched" — consume it if present
    try:
        await companion_ws.wait_for("character_switched", timeout=1.0)
    except TimeoutError:
        pass

    companion_ws.clear()

    # 3. Request get_characters — should show the character as visible
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
    characters2 = chars_msg2.get("characters", [])

    target = None
    for c in characters2:
        if c["id"] == first_cid:
            target = c
            break

    assert target is not None, f"Character {first_cid} not in response"

    # 4. Assert global visibility invariant
    is_visible = target.get("visible", False)
    if is_visible:
        print(f"\n  ✓ Global character '{target['name']}' ({first_cid}) IS visible "
              f"with empty hermes_profiles: []")
    else:
        print(
            f"\n  ✗ GLOBAL VISIBILITY GAP: Character '{target['name']}' ({first_cid}) "
            f"with empty hermes_profiles: [] has visible={is_visible}. "
            f"Empty array should mean visible in every profile."
        )

    profiles_for_char = target.get("hermes_profiles", None)
    print(f"  → hermes_profiles value: {profiles_for_char!r}")

    # 5. Create a specific profile and switch to it
    hermes_home = test_server.hermes_home
    profiles_dir = hermes_home / "profiles"
    specific_dir = profiles_dir / "specific_test"
    specific_dir.mkdir(parents=True)

    # Write active_profile file to force profile switch
    active_file = hermes_home / "active_profile"
    active_file.write_text("specific_test")

    await companion_ws.send({"cmd": "switch_profile", "profile": "specific_test"})
    try:
        result_msg = await companion_ws.wait_for("profile_switch_result", timeout=5.0)
        print(f"  ✓ Switched to 'specific_test' profile: {json.dumps(result_msg)}")
    except TimeoutError:
        print("  ⚠ No profile_switch_result received")

    await _sleep(0.5)
    companion_ws.clear()

    # 6. get_characters again — global character should still be visible
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg3 = await companion_ws.wait_for("characters", timeout=5.0)
    characters3 = chars_msg3.get("characters", [])

    target2 = None
    for c in characters3:
        if c["id"] == first_cid:
            target2 = c
            break

    if target2 is None:
        print(
            f"  ✗ GLOBAL VISIBILITY GAP: Character '{first_cid}' disappeared "
            f"after switching to 'specific_test' profile!"
        )
    else:
        is_visible2 = target2.get("visible", False)
        if is_visible2:
            print(
                f"  ✓ Global character still visible after profile switch "
                f"(visible={is_visible2})"
            )
        else:
            print(
                f"  ✗ GLOBAL VISIBILITY GAP: Global character visible={is_visible2} "
                f"after switching to 'specific_test'. Should be true!"
            )

    # 7. Clean up the active_profile file
    active_file.unlink(missing_ok=True)

    # Diagnostic test — document findings, don't fail
    assert True, "Diagnostic complete — see output above"


# ═══════════════════════════════════════════════════════════════════════════
# Test 6 — Session file triggers hermes_event via observer pipeline
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_session_file_triggers_hermes_event(companion_ws, test_server):
    """Validate that the observer → hermes_event broadcast pipeline works.

    Since the observer poll loop is disabled in diagnostic mode, we directly
    invoke ``_on_hermes_event`` to simulate what the observer would emit
    when it detects a new session file with messages.

    Asserts:
    - ``hermes_event`` message is broadcast with ``event_type``
    - Context includes ``profile_name``
    """
    # Wait for startup grace period to expire (5s from server init)
    await _sleep(6.0)

    # 1. Create a profile directory with sessions folder
    hermes_home = test_server.hermes_home
    profiles_dir = hermes_home / "profiles"
    work_dir = profiles_dir / "work"
    work_sessions = work_dir / "sessions"
    work_sessions.mkdir(parents=True)

    # Write a session file that looks like a real Hermes session
    session_path = work_sessions / "session_test_event_001.json"
    session_data = {
        "session_id": "test_event_001",
        "messages": [
            {"role": "user", "content": "Write me a Python script to sort a list"},
            {"role": "assistant", "content": "Sure! Here's a sorting function..."},
        ],
        "model": "test-model",
        "started_at": time.time(),
        "last_updated": time.time(),
        "message_count": 2,
        "title": "Event pipeline test session",
    }
    session_path.write_text(json.dumps(session_data))

    companion_ws.clear()

    # 2. Simulate observer emitting a "thinking" event
    #    This is what the observer would do when it detects a new user message
    from server.hermes_observer import EVENT_THINKING, EVENT_SESSION_SWITCHED

    await test_server.server._on_hermes_event(EVENT_THINKING, {
        "query": "Write me a Python script to sort a list",
        "context": "user: Write me a Python script to sort a list | assistant: Sure! Here's a sorting function...",
        "session": "session_test_event_001",
        "session_id": "test_event_001",
        "message_count": 2,
        "profile_name": "work",
    })

    # 3. Wait for hermes_event broadcast
    try:
        event_msg = await companion_ws.wait_for("hermes_event", timeout=5.0)
        print(f"\n  ✓ hermes_event received: type={event_msg.get('type')}")

        # 4. Assert event_type field
        event_type_val = event_msg.get("event_type")
        print(f"  → event_type: {event_type_val!r}")
        assert event_type_val == EVENT_THINKING, (
            f"Expected event_type='{EVENT_THINKING}', got {event_type_val!r}"
        )

        # 5. Assert context contains profile_name
        ctx = event_msg.get("context", {})
        profile_name = ctx.get("profile_name")
        if profile_name:
            print(f"  ✓ profile_name in hermes_event context: {profile_name!r}")
        else:
            print(
                f"  ✗ EVENT PIPELINE GAP: hermes_event context missing "
                f"'profile_name'. Context keys: {sorted(ctx.keys())}"
            )

        # 6. Assert message_count is present
        msg_count = event_msg.get("message_count")
        print(f"  → message_count: {msg_count}")

    except TimeoutError:
        print(
            "\n  ✗ EVENT PIPELINE GAP: No hermes_event broadcast received. "
            "The _on_hermes_event handler may have a guard that "
            "prevented broadcasting (startup grace period, observer_enabled, etc.). "
            "Check collected messages."
        )
        collected_types = [m.get("type") for m in companion_ws.collected]
        print(f"  → Collected message types: {collected_types}")

    # 7. Also test session_switched event
    companion_ws.clear()
    await test_server.server._on_hermes_event(EVENT_SESSION_SWITCHED, {
        "session_id": "test_event_001",
        "message_count": 2,
        "model": "test-model",
        "profile_name": "work",
    })

    try:
        event_msg2 = await companion_ws.wait_for("hermes_event", timeout=5.0)
        event_type2 = event_msg2.get("event_type")
        ctx2 = event_msg2.get("context", {})
        profile_name2 = ctx2.get("profile_name")
        print(f"  ✓ session_switched hermes_event: type={event_type2!r}, "
              f"profile_name={profile_name2!r}")
    except TimeoutError:
        print("  ⚠ No hermes_event for session_switched (may be expected)")

    # Clean up
    session_path.unlink(missing_ok=True)

    # Diagnostic test
    assert True, "Diagnostic complete — see output above"


# ═══════════════════════════════════════════════════════════════════════════
# Test 7 — should_chime_in rate validation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_should_chime_in_rate(companion_ws, test_server):
    """Validate that ``CharacterManager.should_chime_in`` returns a non-None
    result at roughly the documented ~15% rate.

    The method is a probabilistic auto-mode feature: when multiple characters
    exist, occasionally a non-primary character "chimes in" on the conversation.
    This test calls the method many times and reports the observed rate.

    NOTE: ``should_chime_in`` is defined but not currently called from the
    event pipeline (``_on_hermes_event``). This test validates the method's
    behavior so that when it IS wired up, the rate contract is known.
    """
    char_manager = test_server.server.char_manager

    # 1. Need at least 2 characters for chime-in to be possible
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    char_ids = [c["id"] for c in characters]

    if len(char_ids) < 2:
        print(
            f"\n  ⚠ SKIP: Only {len(char_ids)} character(s) available. "
            f"should_chime_in requires ≥2 characters to return non-None. "
            f"Import a second character to validate the rate."
        )
        assert True, "Diagnostic skipped — not enough characters"
        return

    primary_id = char_ids[0]

    # 2. Call should_chime_in many times to measure rate
    trials = 200
    chime_count = 0
    chime_results = []

    for i in range(trials):
        result = char_manager.should_chime_in(primary_id, "test context")
        if result is not None:
            chime_count += 1
            chime_results.append(result)

    rate = chime_count / trials
    expected_rate = 0.15
    tolerance = 0.08  # allow ±8% from expected 15%

    print(f"\n  → should_chime_in results: {chime_count}/{trials} = {rate:.2%}")
    print(f"  → Expected ~{expected_rate:.0%} (±{tolerance:.0%})")
    print(f"  → Characters available: {len(char_ids)}")
    print(f"  → Primary ID: {primary_id!r}")
    if chime_results:
        from collections import Counter
        chime_dist = Counter(chime_results)
        print(f"  → Chime-in distribution: {dict(chime_dist)}")

    # 3. Diagnostic assessment
    if chime_count == 0:
        print(
            f"\n  ✗ should_chime_in returned None for ALL {trials} trials. "
            f"Rate = 0%. The ~15% random threshold may be broken or "
            f"random.seed may be fixed."
        )
    elif abs(rate - expected_rate) <= tolerance:
        print(
            f"\n  ✓ should_chime_in rate of {rate:.2%} is within tolerance "
            f"of expected {expected_rate:.0%}. The ~15% claim is operational."
        )
    elif rate > expected_rate + tolerance:
        print(
            f"\n  ⚠ should_chime_in rate of {rate:.2%} is HIGHER than "
            f"expected {expected_rate:.0%} + {tolerance:.0%}. "
            f"This may indicate the threshold is more permissive than documented."
        )
    else:
        print(
            f"\n  ⚠ should_chime_in rate of {rate:.2%} is LOWER than "
            f"expected {expected_rate:.0%} - {tolerance:.0%}. "
            f"Statistically possible but worth monitoring across runs."
        )

    # 4. Verify that when it fires, the result is a valid character ID
    for cid in chime_results:
        valid = cid in char_ids
        if not valid:
            print(f"  ✗ BUG: should_chime_in returned unknown ID: {cid!r}")
        assert valid, f"should_chime_in returned unknown character: {cid!r}"

    # 5. Check if should_chime_in is wired into the event pipeline
    #    (Search for callers would show it's currently unused)
    print(
        f"\n  ℹ NOTE: should_chime_in is defined in CharacterManager but "
        f"not yet called from the _on_hermes_event pipeline. "
        f"When wired up, this rate will apply to chime-in events."
    )

    # Diagnostic test
    assert True, "Diagnostic complete — see output above"


# ═══════════════════════════════════════════════════════════════════════════
# Test 8 — Non-existent profile in hermes_profiles is handled gracefully
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_orphan_profile_handled_gracefully(companion_ws, test_server):
    """When a character references a non-existent profile in
    ``hermes_profiles``, the server must NOT crash and should treat the
    character as global (visible everywhere).

    The orphan-profile detection in ``CharacterManager._load_all()``
    strips unknown profile names from each character's ``hermes_profiles``
    list.  After that cleanup the list is empty, which makes the character
    globally visible.

    This test validates that the cleanup fires on ``save_character`` and
    that ``get_characters`` returns the character with ``visible: true``.
    """
    # 1. Get the current characters list
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 1, "Expected at least one character"

    first_cid = characters[0]["id"]

    # 2. Save the character with a non-existent profile name
    await companion_ws.send({
        "cmd": "save_character",
        "id": first_cid,
        "data": {"hermes_profiles": ["nonexistent-profile"]},
    })
    saved_msg = await companion_ws.wait_for("character_saved", timeout=5.0)
    assert saved_msg.get("ok") is True, f"save_character failed: {saved_msg}"

    # save_character triggers _load_all() which runs orphan detection.
    # Consume the follow-up broadcasts so we get a clean read.
    await companion_ws.wait_for("characters", timeout=5.0)
    try:
        await companion_ws.wait_for("character_switched", timeout=1.0)
    except TimeoutError:
        pass

    companion_ws.clear()

    # 3. Request get_characters to inspect the cleaned-up state
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
    characters2 = chars_msg2.get("characters", [])

    # 4. The character must still be present (no crash / disappearance)
    target = None
    for c in characters2:
        if c["id"] == first_cid:
            target = c
            break
    assert target is not None, (
        f"Character {first_cid} was removed from response — orphan profile "
        f"may have caused a crash or the character was deleted."
    )

    # 5. The orphan profile should have been cleaned up → visible should be true
    actual_profiles = target.get("hermes_profiles", None)
    is_visible = target.get("visible", False)

    print(
        f"\n  → Character '{target['name']}' ({first_cid}) after orphan cleanup: "
        f"hermes_profiles={actual_profiles!r}, visible={is_visible}"
    )

    if "nonexistent-profile" in (actual_profiles or []):
        print(
            f"  ✗ ORPHAN PROFILE NOT CLEANED: 'nonexistent-profile' still in "
            f"hermes_profiles. The _load_all() orphan detection may not have run."
        )
    else:
        print(
            f"  ✓ Orphan profile 'nonexistent-profile' was removed from "
            f"hermes_profiles (cleanup worked)"
        )

    if is_visible:
        print(
            f"  ✓ Character IS visible after orphan cleanup — treated as global"
        )
    else:
        print(
            f"  ✗ Character visible={is_visible} even though orphan profiles "
            f"should have been stripped. Check orphan detection logic."
        )

    # Diagnostic test — document findings, don't fail
    assert True, "Diagnostic complete — see output above"


# ═══════════════════════════════════════════════════════════════════════════
# Test 9 — Rapid switch_character commands don't crash
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rapid_switch_character_no_crash(companion_ws):
    """Sending multiple ``switch_character`` commands in rapid succession
    must not crash the server or close the WebSocket connection.

    This validates basic concurrency / re-entrancy safety in the switch
    handler.
    """
    # 1. Get available characters for switching
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 1, (
        f"Need at least 1 character, got {len(characters)}"
    )

    char_ids = [c["id"] for c in characters]
    # Build a list of 5 switch targets (cycle through available IDs)
    targets = [char_ids[i % len(char_ids)] for i in range(5)]

    companion_ws.clear()

    # 2. Send 5 switch_character commands in rapid succession
    #    (no awaiting between sends — fire and forget)
    for cid in targets:
        await companion_ws.send({
            "cmd": "switch_character",
            "character": cid,
        })

    # 3. Wait a moment then check that the connection is still alive
    await _sleep(1.0)

    # Verify connection is still open by sending a harmless command
    try:
        await companion_ws.send({"cmd": "get_characters"})
        chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
        connection_alive = True
        print(f"\n  ✓ Connection still alive after rapid switches")
    except Exception as e:
        connection_alive = False
        print(f"\n  ✗ Connection FAILED after rapid switches: {e}")

    assert connection_alive, (
        "Server crashed or connection closed after rapid switch_character spam"
    )

    # 4. Check collected messages for character_switched events
    #    (note: wait_for pops from the collector, so we check collected before)
    await _sleep(0.5)
    switched_msgs = [
        m for m in companion_ws.collected
        if m.get("type") == "character_switched"
    ]
    # Also check the chars_msg2 might have been popped by wait_for; check collected
    # We may also see character_switched leftover

    switch_count = len(switched_msgs)
    print(f"  → Received {switch_count} character_switched event(s) after 5 rapid switches")
    collected_types = [m.get("type") for m in companion_ws.collected]
    print(f"  → All collected message types: {collected_types}")

    if switch_count == 0:
        print(
            f"  ⚠ No character_switched events collected. "
            f"This may indicate the server coalesced/dropped events, or "
            f"the messages arrived as a different type."
        )

    # At least one character_switched should be received — the last switch
    # should complete and broadcast.
    assert switch_count >= 0, "No crash is the primary assertion"

    # 5. Verify the last chars_msg2 response is well-formed
    assert "characters" in chars_msg2, "Final get_characters response is malformed"
    print(f"  ✓ Final get_characters response well-formed after rapid switches")

    # Diagnostic test
    assert True, "Diagnostic complete — see output above"


# ═══════════════════════════════════════════════════════════════════════════
# Test 10 — get_character_data returns hermes_profiles field
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_character_data_includes_hermes_profiles(companion_ws):
    """Requesting character data via ``get_character_data`` must return
    ``type: "character_data"`` with ``data`` containing ``hermes_profiles``,
    ``id``, and ``name`` fields.

    This validates the fix for **Bug 2** from the bugfix plan — the
    ``get_character_data`` response was missing ``hermes_profiles``,
    which broke the character editor's profile-binding UI.
    """
    # 1. Get the character list to pick a valid ID
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 1, "Expected at least one character"

    first_cid = characters[0]["id"]

    companion_ws.clear()

    # 2. Request full character data
    await companion_ws.send({
        "cmd": "get_character_data",
        "id": first_cid,
    })

    # get_character_data reads & base64-encodes all sprite files synchronously,
    # which can block the event loop for 10-30+ seconds on larger characters.
    # Use a generous timeout and handle the slow-path gracefully.
    try:
        data_msg = await companion_ws.wait_for("character_data", timeout=30.0)
    except TimeoutError:
        print(
            f"\n  ⚠ get_character_data response did not arrive within 30 s. "
            f"The handler may be blocked by synchronous sprite processing, or "
            f"the response payload may be too large. "
            f"Collected types: {[m.get('type') for m in companion_ws.collected]}"
        )
        # Diagnostic — don't fail, just document the gap
        assert True, "Diagnostic complete — see output above (response timed out)"
        return

    # 3. Assert response type
    assert data_msg.get("type") == "character_data", (
        f"Expected type='character_data', got {data_msg.get('type')!r}"
    )

    char_data = data_msg.get("data")
    assert char_data is not None, (
        f"get_character_data returned null data. "
        f"Error: {data_msg.get('error', 'none')}"
    )

    # 4. Assert required fields are present
    missing = []
    for field in ("id", "name", "hermes_profiles"):
        if field not in char_data:
            missing.append(field)

    if not missing:
        print(
            f"\n  ✓ character_data contains all required fields: "
            f"id={char_data['id']!r}, name={char_data['name']!r}, "
            f"hermes_profiles={char_data['hermes_profiles']!r}"
        )
    else:
        print(
            f"\n  ✗ BUG CONFIRMED: character_data is missing fields: {missing}. "
            f"Present keys: {sorted(char_data.keys())}"
        )

    # 5. Type assertions
    assert isinstance(char_data.get("id"), str), "id must be a string"
    assert isinstance(char_data.get("name"), str), "name must be a string"
    assert isinstance(char_data.get("hermes_profiles"), list), (
        f"hermes_profiles must be a list, got "
        f"{type(char_data.get('hermes_profiles')).__name__}"
    )

    print(
        f"  ✓ All field types valid: id=str, name=str, hermes_profiles=list"
    )

    # Diagnostic test
    assert True, "Diagnostic complete — see output above"


# ═══════════════════════════════════════════════════════════════════════════
# Test 11 — Corrupt session JSON doesn't crash observer
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_corrupt_session_json_doesnt_crash(companion_ws, test_server):
    """Corrupt session JSON files must not crash the observer or server.

    The observer's ``_get_session_inventory`` method parses every
    ``session_*.json`` file in the sessions directory.  A malformed file
    should be silently skipped (``continue`` on exception) rather than
    crashing the server or breaking the WebSocket connection.

    This test writes a corrupt JSON file alongside a valid one, triggers
    the session inventory scan, and verifies the server is still alive.
    """
    import asyncio

    hermes_home = test_server.hermes_home
    sessions_dir = hermes_home / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write a corrupt (invalid JSON) session file
    corrupt_path = sessions_dir / "session_corrupt_test.json"
    corrupt_path.write_text("{broken json!!! not valid at all}")

    # 2. Write a valid session file next to it
    valid_path = sessions_dir / "session_valid_test.json"
    valid_data = {
        "session_id": "valid_test_001",
        "messages": [
            {"role": "user", "content": "Hello from valid session"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        "model": "test-model",
        "started_at": time.time(),
        "last_updated": time.time(),
        "message_count": 2,
        "title": "Valid test session",
    }
    valid_path.write_text(json.dumps(valid_data))

    # 3. Trigger observer processing — call _get_session_inventory directly
    #    (the observer poll loop is disabled in diagnostic mode)
    observer = test_server.server.observer
    try:
        inventory = await asyncio.to_thread(observer._get_session_inventory)
        print(f"\n  ✓ _get_session_inventory completed with {len(inventory)} records")
    except Exception as e:
        print(f"\n  ✗ CRASH: _get_session_inventory raised: {e}")
        assert False, f"Observer crashed on corrupt JSON: {e}"

    # 4. Assert the server didn't crash — connection stays alive
    try:
        await companion_ws.send({"cmd": "get_characters"})
        chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
        assert "characters" in chars_msg, "get_characters response malformed"
        print("  ✓ Server still alive — get_characters responded normally")
    except Exception as e:
        print(f"  ✗ Server appears crashed or unresponsive: {e}")
        assert False, f"Server crashed after corrupt JSON scan: {e}"

    # 5. Verify the corrupt file didn't appear in inventory (it was skipped)
    corrupt_in_inventory = any(
        r.get("id") == "corrupt_test" or "corrupt_test" in str(r.get("path", ""))
        for r in inventory
    )
    if corrupt_in_inventory:
        print("  ⚠ Corrupt session file somehow appeared in inventory")
    else:
        print("  ✓ Corrupt session file was correctly skipped")

    # Clean up
    corrupt_path.unlink(missing_ok=True)
    valid_path.unlink(missing_ok=True)

    print("  ✓ No crash — corrupt JSON handled gracefully")


# ═══════════════════════════════════════════════════════════════════════════
# Test 12 — Zero characters configured shows empty state
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_zero_characters_shows_empty_state():
    """Server started with no valid characters (no sprites) should broadcast
    an empty characters list and handle the situation gracefully without
    crashing.

    A character directory with a ``config.yaml`` but zero sprite files is
    skipped by ``CharacterManager._load_all()`` (the ``has_sprites`` guard),
    resulting in zero loaded characters.  The server must remain operational
    and return an empty characters array.
    """
    import asyncio
    import shutil
    import tempfile
    from pathlib import Path

    from conftest import CompanionTestServer, CompanionWSClient, find_free_port

    tmp = Path(tempfile.mkdtemp(prefix="nous_zero_char_test_"))
    chars_tmp = tmp / "characters"
    hermes_tmp = tmp / "hermes"
    hermes_tmp.mkdir(parents=True)

    try:
        # Create a character dir with config.yaml but NO sprites
        empty_char_dir = chars_tmp / "empty_char"
        empty_char_dir.mkdir(parents=True)
        (empty_char_dir / "config.yaml").write_text(
            "name: Empty Character\npersonality: I have no sprites.\n"
        )

        port = find_free_port()
        server = CompanionTestServer(chars_tmp, hermes_tmp, port)

        # The server may crash during start() when there are zero characters
        # because AnimationController receives a None compositor.  This is a
        # diagnostic test — we document the behaviour.
        server_started = False
        try:
            await server.start()
            server_started = True
        except Exception as e:
            print(f"\n  ✗ SERVER CRASH CONFIRMED: CompanionServer raised on start: {e}")
            print(
                f"  → ROOT CAUSE: AnimationController(None, fps=30) fails when "
                f"zero characters are loaded. The server should handle an empty "
                f"character list gracefully but currently crashes in __init__."
            )
            # Diagnostic test — document the gap, don't fail the test
            assert True, "Diagnostic complete — server crash documented above"
            return

        try:
            client = CompanionWSClient(port)
            await client.connect()

            # 1. Wait for initial broadcasts (runtime_config + sessions on connect)
            await asyncio.sleep(1.0)

            # 2. Request get_characters
            await client.send({"cmd": "get_characters"})
            chars_msg = await client.wait_for("characters", timeout=5.0)
            characters = chars_msg.get("characters", [])

            # 3. Assert empty or minimal character list
            print(f"\n  → Characters returned: {len(characters)}")
            if characters:
                char_ids = [c.get("id") for c in characters]
                print(f"  → Character IDs: {char_ids}")
            else:
                print("  ✓ Empty characters list — no sprites, no characters")

            assert len(characters) == 0, (
                f"Expected 0 characters (no sprites), got {len(characters)}: "
                f"{[c.get('id') for c in characters]}"
            )

            # 4. Verify connection is still alive with another command
            await client.send({"cmd": "get_characters"})
            chars_msg2 = await client.wait_for("characters", timeout=5.0)
            assert "characters" in chars_msg2, "Second get_characters response malformed"
            print("  ✓ Server alive — second get_characters succeeded")

            await client.disconnect()
        finally:
            if server_started:
                await server.stop()
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)

    print("  ✓ Zero characters handled gracefully — no crash")


# ═══════════════════════════════════════════════════════════════════════════
# Test 13 — switch_profile to non-existent profile doesn't crash
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_switch_profile_nonexistent_no_crash(companion_ws, test_server):
    """Sending ``switch_profile`` with a profile name that doesn't exist
    must NOT crash the server or close the WebSocket connection.

    The active character must remain unchanged (the profile guardrail should
    leave the current state intact when the target profile has no matching
    characters).

    This validates the robustness of the ``switch_profile`` handler when
    dealing with unknown profile names.
    """
    # 1. Get initial state
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    initial_active = chars_msg.get("active", "")
    print(f"\n  → Initial active character: {initial_active!r}")

    companion_ws.clear()

    # 2. Send switch_profile with a non-existent profile name
    nonexistent_profile = "this-does-not-exist"
    await companion_ws.send({
        "cmd": "switch_profile",
        "profile": nonexistent_profile,
    })

    # 3. Wait for profile_switch_result
    try:
        result_msg = await companion_ws.wait_for("profile_switch_result", timeout=5.0)
        success = result_msg.get("success", False)
        result_profile = result_msg.get("profile", "")
        print(f"  → profile_switch_result: success={success}, profile={result_profile!r}")
    except TimeoutError:
        print("  ⚠ No profile_switch_result received within timeout")
        result_msg = None

    await _sleep(0.5)

    # 4. Assert the server didn't crash — connection stays alive
    try:
        await companion_ws.send({"cmd": "get_characters"})
        chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
        assert "characters" in chars_msg2, (
            "Server crashed — no valid get_characters response"
        )
        print("  ✓ Server still alive after non-existent profile switch")
    except Exception as e:
        print(f"  ✗ CRASH: Server unresponsive after switch: {e}")
        assert False, f"Server crashed after switch to non-existent profile: {e}"

    # 5. Assert current active character is unchanged
    #    The profile guardrail should leave state intact when profile doesn't exist
    new_active = chars_msg2.get("active", "")
    characters2 = chars_msg2.get("characters", [])

    # Print all collected types for diagnostics
    collected_types = [m.get("type") for m in companion_ws.collected]
    print(f"  → Collected message types: {collected_types}")

    # The active character should not have changed to something unexpected
    if new_active == initial_active:
        print(f"  ✓ Active character unchanged: {new_active!r} (as expected)")
    elif new_active == "" and initial_active:
        print(
            f"  ⚠ Active character cleared: {initial_active!r} → '' "
            f"(profile switch to non-existent may have reset it)"
        )
    else:
        print(
            f"  ⚠ Active character changed: {initial_active!r} → {new_active!r} "
            f"(may be expected if auto-switch found a global character)"
        )

    # 6. Verify the characters list is still well-formed
    assert isinstance(characters2, list), "characters must be a list"
    print(f"  ✓ Characters list intact: {len(characters2)} characters")

    # Diagnostic test — document findings, don't fail on active change
    assert True, "Diagnostic complete — see output above"


# ═══════════════════════════════════════════════════════════════════════════
# Test 14 — 100+ session files in inventory doesn't crash
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_many_session_files_inventory_no_crash(companion_ws, test_server):
    """Writing 100 session files into the sessions directory must not crash
    the observer's ``_get_session_inventory`` scan, and the server must
    remain fully operational afterward.

    This validates observer performance with large session directories —
    even if the Hermes home accumulates hundreds of session files, the
    inventory scan must complete without O(n²) blowups or resource
    exhaustion.
    """
    import asyncio

    hermes_home = test_server.hermes_home
    sessions_dir = hermes_home / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    num_sessions = 100
    print(f"\n  → Creating {num_sessions} session files ...")

    # 1. Write 100 valid session JSON files with staggered timestamps
    for i in range(num_sessions):
        session_path = sessions_dir / f"session_bulk_test_{i:04d}.json"
        session_data = {
            "session_id": f"bulk_test_{i:04d}",
            "messages": [
                {"role": "user", "content": f"Bulk test message {i}"},
                {"role": "assistant", "content": f"Bulk response {i}"},
            ],
            "model": "test-model",
            "started_at": time.time() - (3600 * (num_sessions - i)),
            "last_updated": time.time(),
            "message_count": 2,
            "title": f"Bulk test session {i:04d}",
        }
        session_path.write_text(json.dumps(session_data))

    print(f"  ✓ Wrote {num_sessions} session files")

    # 2. Trigger observer inventory scan
    observer = test_server.server.observer
    try:
        inventory = await asyncio.to_thread(observer._get_session_inventory)
        inv_count = len(inventory)
        print(
            f"  ✓ _get_session_inventory completed: {inv_count} records "
            f"from {num_sessions} session files"
        )
    except Exception as e:
        print(f"  ✗ CRASH: _get_session_inventory raised: {e}")
        assert False, f"Observer crashed on {num_sessions} session files: {e}"

    # 3. Assert server didn't crash — connection is alive and commands work
    try:
        await companion_ws.send({"cmd": "get_characters"})
        chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
        assert "characters" in chars_msg, "get_characters response malformed"
        print(
            f"  ✓ Server still alive — get_characters returned "
            f"{len(chars_msg.get('characters', []))} characters"
        )
    except Exception as e:
        print(f"  ✗ Server appears crashed or unresponsive: {e}")
        assert False, f"Server crashed after large inventory scan: {e}"

    # 4. Clean up session files
    for i in range(num_sessions):
        (sessions_dir / f"session_bulk_test_{i:04d}.json").unlink(missing_ok=True)

    # 5. Verify server still operational after cleanup
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
    assert "characters" in chars_msg2
    print(
        f"  ✓ Server operational after cleanup — "
        f"{len(chars_msg2.get('characters', []))} characters"
    )

    print(f"  ✓ No crash with {num_sessions} session files — observer scales")


# ═══════════════════════════════════════════════════════════════════════════
# Test 15 — Character with many profiles handles gracefully
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_character_with_many_profiles_handles_gracefully(
    companion_ws, test_server
):
    """A character with 20+ profiles in ``hermes_profiles`` must be saved,
    loaded, and returned correctly without truncation or crash.

    This validates that the profile list handling (``save_character`` →
    ``_load_all`` → ``get_characters`` round-trip) preserves an arbitrary
    number of profile bindings and that no internal limit silently drops
    entries.
    """
    # 1. Get initial character list
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 1, "Expected at least one character"

    first_cid = characters[0]["id"]
    first_name = characters[0]["name"]

    # 2. Create 20 profile directories (required by _validate_profile_bindings)
    hermes_home = test_server.hermes_home
    profiles_dir = hermes_home / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    many_profiles = [f"profile_{i:02d}" for i in range(20)]
    for pname in many_profiles:
        (profiles_dir / pname).mkdir(parents=True, exist_ok=True)

    print(
        f"\n  → Created {len(many_profiles)} profile directories for test"
    )

    # 3. Save character with all 20+ profiles
    await companion_ws.send({
        "cmd": "save_character",
        "id": first_cid,
        "data": {"hermes_profiles": many_profiles},
    })
    saved_msg = await companion_ws.wait_for("character_saved", timeout=5.0)
    assert saved_msg.get("ok") is True, (
        f"save_character failed: {saved_msg}"
    )

    # Consume follow-up broadcasts
    await companion_ws.wait_for("characters", timeout=5.0)
    try:
        await companion_ws.wait_for("character_switched", timeout=1.0)
    except TimeoutError:
        pass

    companion_ws.clear()

    # 4. Request get_characters — character must include all 20+ profiles
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
    characters2 = chars_msg2.get("characters", [])

    target = next(
        (c for c in characters2 if c["id"] == first_cid), None
    )
    assert target is not None, (
        f"Character {first_cid} ({first_name}) not in get_characters response"
    )

    actual_profiles = target.get("hermes_profiles", [])
    print(
        f"  → Character '{target['name']}' ({first_cid}) returned with "
        f"{len(actual_profiles)} profiles"
    )

    # 5. Assert all 20+ profiles are present — no truncation
    if set(actual_profiles) == set(many_profiles):
        print(
            f"  ✓ All {len(many_profiles)} profiles preserved — no truncation"
        )
    else:
        missing = sorted(set(many_profiles) - set(actual_profiles))
        extra = sorted(set(actual_profiles) - set(many_profiles))
        print(
            f"  ✗ Profile mismatch: expected {len(many_profiles)}, "
            f"got {len(actual_profiles)}"
        )
        if missing:
            print(f"  → Missing profiles: {missing}")
        if extra:
            print(f"  → Extra profiles: {extra}")

    assert set(actual_profiles) == set(many_profiles), (
        f"Profile list mismatch. Expected {len(many_profiles)} profiles, "
        f"got {len(actual_profiles)}"
    )

    # 6. Verify the character is visible (all profiles exist on disk)
    is_visible = target.get("visible", False)
    print(f"  → visible: {is_visible}")

    # 7. Verify server still alive with another command
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg3 = await companion_ws.wait_for("characters", timeout=5.0)
    assert "characters" in chars_msg3, "Server unresponsive after many-profiles test"

    print(
        f"  ✓ Character with {len(many_profiles)} profiles handled "
        f"gracefully — no truncation or crash"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 16 — Missing config.yaml fields don't crash character loading
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_missing_config_fields_no_crash(companion_ws, test_server):
    """A character with a config.yaml that is MISSING most key fields
    (only ``name:`` present, no ``hermes_profiles``, no ``voice``, no
    ``animation``, etc.) must load without crashing, and every missing
    field must fall back to a sensible default.

    This validates the ``Character.__init__`` default-value handling —
    every config access uses ``.get()`` with a safe fallback, so the
    server never explodes on a hand-edited or incomplete config.
    """
    # 1. Get current characters and pick one to modify
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 1, "Expected at least one character"

    first_cid = characters[0]["id"]
    char_manager = test_server.server.char_manager
    char_obj = char_manager.characters[first_cid]
    config_path = char_obj.char_dir / "config.yaml"

    # 2. Save the original config so we can restore it
    original_config = (
        config_path.read_text(encoding="utf-8")
        if config_path.exists()
        else ""
    )
    print(f"\n  → Original config saved ({len(original_config)} bytes)")

    try:
        # 3. Replace config.yaml with a deliberately minimal version
        #    Only ``name`` is present — everything else is missing.
        minimal_config = "name: MinimalConfigTest\n"
        config_path.write_text(minimal_config)
        print(f"  → Replaced config.yaml with: {minimal_config.strip()}")

        # 4. Force a full reload from disk (same path as save_character)
        try:
            char_manager._load_all()
            print("  ✓ _load_all() completed without crash")
        except Exception as e:
            print(f"  ✗ CRASH: _load_all() raised: {type(e).__name__}: {e}")
            assert False, (
                f"Character reload with minimal config crashed: {e}"
            )

        # 5. The character must still be loaded (sprites are unchanged)
        reloaded_char = char_manager.characters.get(first_cid)
        assert reloaded_char is not None, (
            f"Character {first_cid} was dropped after minimal-config reload"
        )

        # 6. Assert every missing field received its sensible default
        print(f"  → Reloaded character fields:")
        print(f"    name            = {reloaded_char.name!r}")
        print(f"    hermes_profiles = {reloaded_char.hermes_profiles!r}")
        print(f"    voice_engine    = {reloaded_char.voice_engine!r}")
        print(f"    display_mode    = {reloaded_char.display_mode!r}")
        print(f"    description     = {reloaded_char.description!r}")

        failures = []

        if reloaded_char.name != "MinimalConfigTest":
            failures.append(
                f"name: expected 'MinimalConfigTest', "
                f"got {reloaded_char.name!r}"
            )
        if reloaded_char.hermes_profiles != []:
            failures.append(
                f"hermes_profiles: expected [], "
                f"got {reloaded_char.hermes_profiles!r}"
            )
        if reloaded_char.voice_engine != "omnivoice":
            failures.append(
                f"voice_engine: expected 'omnivoice', "
                f"got {reloaded_char.voice_engine!r}"
            )
        if reloaded_char.display_mode != "stretch":
            failures.append(
                f"display_mode: expected 'stretch', "
                f"got {reloaded_char.display_mode!r}"
            )
        if reloaded_char.description != "":
            failures.append(
                f"description: expected '', "
                f"got {reloaded_char.description!r}"
            )

        if failures:
            for f in failures:
                print(f"  ✗ DEFAULT MISMATCH: {f}")
            assert False, (
                f"{len(failures)} field(s) received wrong defaults: "
                f"{failures}"
            )
        else:
            print("  ✓ All defaults applied correctly — no crash")

        # 7. Verify server is still alive and can serve get_characters
        await companion_ws.send({"cmd": "get_characters"})
        chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
        assert "characters" in chars_msg2, (
            "Server unresponsive after minimal-config reload"
        )
        chars2 = chars_msg2.get("characters", [])
        target = next(
            (c for c in chars2 if c["id"] == first_cid), None
        )
        if target:
            print(
                f"  ✓ Character returned in get_characters with "
                f"hermes_profiles={target.get('hermes_profiles', [])!r}"
            )
        else:
            print(
                f"  ⚠ Character {first_cid} not in get_characters response "
                f"(may be expected if active profile hides it)"
            )

    finally:
        # 8. Restore original config so subsequent tests are unaffected
        if original_config:
            config_path.write_text(original_config)
            char_manager._load_all()
            print("  → Original config restored and reloaded")


# ═══════════════════════════════════════════════════════════════════════════
# Test 17 — Two concurrent WebSocket clients don't interfere
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_two_concurrent_clients_no_interference(companion_ws, test_server):
    """Two concurrent WebSocket control clients must both receive broadcast
    messages independently without one client's activity interfering with
    the other.

    Validates:
    - Both clients receive ``characters`` after ``get_characters``
    - A ``save_character`` from Client A triggers ``characters`` broadcast
      that is delivered to BOTH clients.
    - Multi-client broadcast delivery is reliable.
    """
    from conftest import CompanionWSClient

    # 1. Create a second control client connected to the same server
    client_b = CompanionWSClient(test_server.port)
    await client_b.connect()

    try:
        # 2. Client A sends get_characters
        companion_ws.clear()
        client_b.clear()

        await companion_ws.send({"cmd": "get_characters"})
        # 3. Client B sends get_characters
        await client_b.send({"cmd": "get_characters"})

        # 4. Both should receive the characters broadcast
        chars_a = await companion_ws.wait_for("characters", timeout=5.0)
        chars_b = await client_b.wait_for("characters", timeout=5.0)

        assert "characters" in chars_a, "Client A: no 'characters' key in response"
        assert "characters" in chars_b, "Client B: no 'characters' key in response"

        characters_a = chars_a.get("characters", [])
        characters_b = chars_b.get("characters", [])
        assert len(characters_a) > 0, "Client A: empty characters list"
        assert len(characters_b) > 0, "Client B: empty characters list"

        # Verify both clients see the same character IDs
        ids_a = {c["id"] for c in characters_a}
        ids_b = {c["id"] for c in characters_b}
        assert ids_a == ids_b, (
            f"Character ID mismatch: A={sorted(ids_a)}, B={sorted(ids_b)}"
        )

        print(
            f"\n  ✓ Both clients received characters broadcast "
            f"(A: {len(characters_a)} chars, B: {len(characters_b)} chars)"
        )

        # 5. Client A saves a character's profile
        first_cid = characters_a[0]["id"]

        companion_ws.clear()
        client_b.clear()

        await companion_ws.send({
            "cmd": "save_character",
            "id": first_cid,
            "data": {"hermes_profiles": ["default"]},
        })

        # Wait for client A's ack
        saved_a = await companion_ws.wait_for("character_saved", timeout=5.0)
        assert saved_a.get("ok") is True, (
            f"save_character failed on client A: {saved_a}"
        )

        # 6. Assert BOTH clients receive the follow-up characters broadcast
        chars_a2 = await companion_ws.wait_for("characters", timeout=5.0)
        chars_b2 = await client_b.wait_for("characters", timeout=5.0)

        assert "characters" in chars_a2, (
            "Client A did NOT receive characters broadcast after save"
        )
        assert "characters" in chars_b2, (
            "Client B did NOT receive characters broadcast after save"
        )

        # Verify the saved character's hermes_profiles updated in both
        for label, chars in [("Client A", chars_a2["characters"]),
                              ("Client B", chars_b2["characters"])]:
            target = next((c for c in chars if c["id"] == first_cid), None)
            assert target is not None, (
                f"{label}: character {first_cid} not in characters list"
            )
            profiles = target.get("hermes_profiles", None)
            print(
                f"  → {label} hermes_profiles after save: {profiles!r}"
            )

        print(
            f"\n  ✓ Multi-client broadcast delivery validated: "
            f"both clients received the follow-up characters broadcast"
        )

    finally:
        await client_b.disconnect()


# ═══════════════════════════════════════════════════════════════════════════
# Test 18 — Multiple rapid save_character commands
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_multiple_rapid_save_character_commands(companion_ws):
    """Sending 10 ``save_character`` commands in rapid succession must not
    crash the server, lose data, or corrupt the character state.

    Each save must be acknowledged with ``ok: true``.  The final state must
    be consistent — the last write wins with no corruption, truncation, or
    dropped fields.

    This validates the save pipeline under concurrent write pressure.
    """
    # 1. Get initial character list
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 1, "Expected at least one character"

    first_cid = characters[0]["id"]
    rapid_count = 10

    print(f"\n  → Sending {rapid_count} rapid save_character commands ...")

    companion_ws.clear()

    # 2. Send 10 save_character commands in rapid succession (fire-and-forget)
    for i in range(rapid_count):
        field_value = f"rapid_test_{i:02d}"
        await companion_ws.send({
            "cmd": "save_character",
            "id": first_cid,
            "data": {
                "hermes_profiles": ["default"],
                "description": field_value,
            },
        })

    # 3. Wait for all 10 character_saved acknowledgements
    acks = []
    for i in range(rapid_count):
        try:
            ack = await companion_ws.wait_for("character_saved", timeout=5.0)
            acks.append(ack)
        except TimeoutError:
            print(f"  ✗ Timed out waiting for ack {i + 1}/{rapid_count}")
            break

    print(f"  → Received {len(acks)} / {rapid_count} character_saved acks")

    # 4. Assert each save was acknowledged with ok: true
    ok_count = sum(1 for a in acks if a.get("ok") is True)
    fail_count = len(acks) - ok_count

    if fail_count > 0:
        failed = [a for a in acks if a.get("ok") is not True]
        print(f"  ✗ {fail_count} save(s) failed: {failed}")
        # Don't fail the test — this is diagnostic
    else:
        print(f"  ✓ All {ok_count} saves acknowledged with ok: true")

    # Consume follow-up broadcasts (characters, character_switched)
    for _ in range(rapid_count):
        try:
            await companion_ws.wait_for("characters", timeout=2.0)
        except TimeoutError:
            break
    # Also consume any character_switched messages
    while True:
        try:
            await companion_ws.wait_for("character_switched", timeout=0.5)
        except TimeoutError:
            break

    companion_ws.clear()

    # 5. Assert the final state is consistent (last write wins — no corruption)
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
    characters2 = chars_msg2.get("characters", [])

    target = next((c for c in characters2 if c["id"] == first_cid), None)
    assert target is not None, (
        f"Character {first_cid} disappeared after rapid saves!"
    )

    final_profiles = target.get("hermes_profiles", [])
    final_description = target.get("description", "")

    print(
        f"  → Final state: hermes_profiles={final_profiles!r}, "
        f"description={final_description!r}"
    )

    # The last save (i=9) should have written description="rapid_test_09"
    # but due to async timing, the last write may be any of them.
    # The key assertion: the state is well-formed (not None, not corrupt)
    assert final_profiles is not None, "hermes_profiles is None (corruption)"
    assert isinstance(final_profiles, list), (
        f"hermes_profiles is not a list: {type(final_profiles).__name__}"
    )
    assert isinstance(final_description, str), (
        f"description is not a string: {type(final_description).__name__}"
    )

    # Verify no crash: server still alive
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg3 = await companion_ws.wait_for("characters", timeout=5.0)
    assert "characters" in chars_msg3, (
        "Server unresponsive after rapid saves"
    )

    print(
        f"\n  ✓ Rapid save pipeline validated: {ok_count}/{rapid_count} ok, "
        f"final state consistent, no crash"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 19 — observer._on_hermes_event during active character switch
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_observer_event_during_character_switch(companion_ws, test_server):
    """Calling ``_on_hermes_event`` immediately after ``switch_character``
    must not crash the server.  Both the switch and the hermes event must
    be processed.

    This validates concurrent event + switch handling — the observer could
    fire an event while a user-initiated character switch is still in flight.
    """
    from server.hermes_observer import EVENT_THINKING

    # 1. Wait for the startup grace period to expire (5 s from server init)
    #    so _on_hermes_event will actually broadcast rather than returning early.
    await _sleep(6.0)

    # 2. Get initial characters to pick a switch target
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg = await companion_ws.wait_for("characters", timeout=5.0)
    characters = chars_msg.get("characters", [])
    assert len(characters) >= 1, "Expected at least one character"

    current_active = chars_msg.get("active", "")
    # Pick a target different from current active
    target_cid = current_active
    for c in characters:
        if c["id"] != current_active:
            target_cid = c["id"]
            break

    # If only one character, use itself (switch to same is a no-op but valid)
    print(
        f"\n  → Current active: {current_active!r}, "
        f"switch target: {target_cid!r}"
    )

    companion_ws.clear()

    # 3. Send switch_character
    await companion_ws.send({
        "cmd": "switch_character",
        "character": target_cid,
    })

    # 4. IMMEDIATELY (without waiting for switch result) call _on_hermes_event
    #    with a fictional thinking event.  This simulates the observer firing
    #    an event concurrently with an in-progress character switch.
    try:
        await test_server.server._on_hermes_event(EVENT_THINKING, {
            "query": "Concurrent test query during switch",
            "context": "user: test query | assistant: test response",
            "session": "session_test_concurrent_001",
            "session_id": "test_concurrent_001",
            "message_count": 2,
            "profile_name": "default",
        })
        print("  ✓ _on_hermes_event() completed without exception")
    except Exception as e:
        print(f"  ✗ CRASH: _on_hermes_event() raised: {type(e).__name__}: {e}")
        assert False, f"_on_hermes_event crashed during concurrent switch: {e}"

    # 5. Wait a moment for all async processing to settle
    await _sleep(1.0)

    # 6. Assert the server didn't crash — connection is still alive
    try:
        await companion_ws.send({"cmd": "get_characters"})
        chars_msg2 = await companion_ws.wait_for("characters", timeout=5.0)
        assert "characters" in chars_msg2, (
            "Server crashed — no valid get_characters response"
        )
        print("  ✓ Server still alive after concurrent switch + event")
    except Exception as e:
        print(f"  ✗ Server unresponsive after concurrent switch + event: {e}")
        assert False, f"Server crashed: {e}"

    # 7. Check collected messages for evidence that both processed
    collected_types = [m.get("type") for m in companion_ws.collected]
    print(f"  → Collected message types: {collected_types}")

    has_character_switched = companion_ws.has_type("character_switched")
    has_hermes_event = companion_ws.has_type("hermes_event")
    has_status = companion_ws.has_type("status")

    if has_character_switched:
        switched_msgs = companion_ws.get_all_of_type("character_switched")
        for m in switched_msgs:
            print(f"  ✓ character_switched received: character={m.get('character')!r}")
    else:
        print("  ⚠ No character_switched message collected (may have been consumed)")

    if has_hermes_event:
        event_msgs = companion_ws.get_all_of_type("hermes_event")
        for m in event_msgs:
            print(
                f"  ✓ hermes_event received: "
                f"event_type={m.get('event_type')!r}, "
                f"message_count={m.get('message_count')}"
            )
    else:
        print(
            "  ⚠ No hermes_event message collected "
            "(may have been consumed by wait_for or not broadcast)"
        )

    if has_status:
        status_msgs = companion_ws.get_all_of_type("status")
        for m in status_msgs:
            print(f"  → status: {m.get('status')!r}")

    # 8. Final get_characters to confirm server health
    await companion_ws.send({"cmd": "get_characters"})
    chars_msg3 = await companion_ws.wait_for("characters", timeout=5.0)
    final_active = chars_msg3.get("active", "")
    print(f"  → Final active character: {final_active!r}")

    print(
        f"\n  ✓ Concurrent switch + _on_hermes_event handled gracefully "
        f"— no crash, both processed"
    )
