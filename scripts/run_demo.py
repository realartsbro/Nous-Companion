"""Connect to companion server WebSocket, load scene, play it."""
import asyncio
import json
import websockets
import sys

WS_URL = "ws://localhost:8765"

async def set_settings(ws, **kwargs):
    """Send multiple set_setting commands."""
    for key, value in kwargs.items():
        await ws.send(json.dumps({"cmd": "set_setting", "key": key, "value": value}))

async def flash(ws, color="#ff0000", strength=0.8, duration=0.4):
    """Toggle colorize ON for a flash, then OFF."""
    await set_settings(ws, colorize_enabled=True, colorize_color=color, colorize_strength=strength)
    await asyncio.sleep(duration)
    await set_settings(ws, colorize_enabled=False)
    await asyncio.sleep(0.3)

async def boot_sequence(ws):
    """Simulate a system boot-up: heavy static → clean reveal."""
    # Phase 1 — All effects ON for heavy static/noise look
    await set_settings(ws,
        show_scanlines=True,
        show_grain=True,
        show_interference=True,
        show_analog_bleed=True,
        colorize_enabled=True,
        colorize_color="#00ff66",  # terminal green
        colorize_strength=0.7,
    )
    await asyncio.sleep(0.6)

    # Phase 2 — Interference drops (system reaching stable state)
    await set_settings(ws, show_interference=False)
    await asyncio.sleep(0.2)

    # Phase 3 — Scanlines and grain drop
    await set_settings(ws, show_scanlines=False, show_grain=False)
    await asyncio.sleep(0.2)

    # Phase 4 — Analog bleed drops, colorize fades
    await set_settings(ws,
        show_analog_bleed=False,
        colorize_enabled=False,
        colorize_strength=0.0,
    )
    await asyncio.sleep(0.3)

async def run_demo():
    print(f"Connecting to {WS_URL}...")
    try:
        ws = await websockets.connect(WS_URL, ping_interval=None)
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        print("  Is the companion app running?")
        sys.exit(1)

    print("✓ Connected. Loading scene...")

    # Load scene
    await ws.send(json.dumps({
        "cmd": "load_scene",
        "path": "demo-scenes/demo-final-v3.nous-scene.json"
    }))
    response = await ws.recv()
    result = json.loads(response)
    print(f"  Load result: {json.dumps(result, indent=2)}")

    if not result.get("ok"):
        print(f"✗ Scene load failed: {result.get('error')}")
        await ws.close()
        sys.exit(1)

    print(f"\n✓ Scene loaded: {result['scene_count']} cues, {result['tts_generated']} voice files loaded")
    print(f"  TTS failed: {result['tts_failed']}")
    print()

    # ── Countdown: 3 red flashes ───────────────────────────── #
    print("3...")
    await flash(ws, duration=0.4)
    print("2...")
    await flash(ws, duration=0.4)
    print("1...")
    await flash(ws, duration=0.4)
    print("INITIALIZING...")

    # ── Show the real app splash screen ─────────────────────── #
    await ws.send(json.dumps({
        "cmd": "show_splash",
        "visible": True,
        "message": "Initializing"
    }))
    await asyncio.sleep(1.8)
    await ws.send(json.dumps({
        "cmd": "show_splash",
        "visible": True,
        "message": "Loading"
    }))
    await asyncio.sleep(1.8)
    await ws.send(json.dumps({
        "cmd": "show_splash",
        "visible": True,
        "message": "Ready"
    }))
    await asyncio.sleep(1.0)

    # ── Fade splash away & start demo ───────────────────────── #
    await ws.send(json.dumps({
        "cmd": "show_splash",
        "visible": False,
    }))
    await asyncio.sleep(0.5)
    print("GO!")

    await ws.send(json.dumps({"cmd": "play_scene"}))
    play_result = json.loads(await ws.recv())

    if play_result.get("ok"):
        print("\n✓ Playback started!\n")
    else:
        print(f"✗ Play failed: {play_result.get('error')}")

    # Listen for scene events
    try:
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=90)
            data = json.loads(msg)
            if data.get("type") == "scene_complete":
                print(f"✓ Scene complete!")
                break
            elif data.get("type") == "scene_cue":
                t = data['time']
                expr = data.get('expression', '?')
                line = data.get('line', '')[:55]
                markers = {0: "▶ ESTABLISHMENT", 1: "  SYSTEM RESPONSE",
                           3: "  PROMPTBOY", 4: "  LOBSTER",
                           7: "▶ COLLAPSE", 8: "  LAST WORD"}
                marker = markers.get(data['index'], "")
                print(f"  [{t:5.1f}s] {expr:>10} {line:<55} {marker}")
            elif data.get("type") == "scene_error":
                print(f"\n✗ Scene error: {data.get('error')}")
                break
    except asyncio.TimeoutError:
        print("\n⚠ Timed out")
    except websockets.ConnectionClosed:
        print("\n⚠ Connection closed")

    await ws.close()
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(run_demo())
