"""Test the WebSocket server with a mock client."""

import sys
import asyncio
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import websockets
from server.companion_server import CompanionServer

CHAR_DIR = Path(__file__).parent.parent / "characters" / "default"


async def test_client():
    """Connect to the server and verify messages."""
    uri = "ws://127.0.0.1:8765"

    async with websockets.connect(uri) as ws:
        # Should receive initial idle frame
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(msg)

        print(f"[1] Received initial event: type={data['type']}")
        assert data["type"] == "idle", f"Expected idle, got {data['type']}"
        assert data["frame"], "Expected frame data"
        assert len(data["frame"]) > 100, "Frame base64 too short"
        print(f"    Frame base64 length: {len(data['frame'])} chars")
        print(f"    Text: '{data['text']}'")

        # Receive expression event
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(msg)
        print(f"\n[2] Received event: type={data['type']}")
        print(f"    Text: '{data['text']}'")
        print(f"    Frame present: {bool(data.get('frame'))}")

        # Receive thinking event
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(msg)
        print(f"\n[3] Received event: type={data['type']}")
        assert data["type"] == "thinking"

        # Receive another expression
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(msg)
        print(f"\n[4] Received event: type={data['type']}")
        print(f"    Text: '{data['text']}'")

        # Final idle
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(msg)
        print(f"\n[5] Received event: type={data['type']}")
        assert data["type"] == "idle"

        print("\nAll server events received correctly!")


async def run_test():
    server = CompanionServer(CHAR_DIR)

    # Start server in background
    server_task = asyncio.create_task(server.start())
    await asyncio.sleep(1)  # Wait for server to start

    try:
        # Run demo sequence + test client concurrently
        async def demo():
            await asyncio.sleep(1)
            await demo_sequence(server)

        await asyncio.gather(demo(), test_client())
    finally:
        server_task.cancel()


async def demo_sequence(server: CompanionServer):
    """Trigger test expressions."""
    print("\n--- Triggering expressions ---")
    await asyncio.sleep(1)
    await server.show_expression(
        base_head="neutral", eyes="open", mouth="smile",
        text="Hello! Ready to go.", duration_ms=3000,
    )
    await asyncio.sleep(1)
    await server.show_thinking()
    await asyncio.sleep(1)
    await server.show_expression(
        base_head="thinking", eyes="wide", mouth="open_talk",
        text="Interesting question!", duration_ms=3000,
    )
    await asyncio.sleep(1)
    await server.show_idle()


if __name__ == "__main__":
    asyncio.run(run_test())
