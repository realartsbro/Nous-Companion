"""
Nous Companion — Demo Server (v2)

Usage:
  python scripts/demo_server.py                    # Start server (wait for renderer)
  python scripts/demo_server.py --test             # Run with test audio
  python scripts/demo_server.py --audio path.wav   # Start with audio file
  python scripts/demo_server.py --expression serious
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from server.companion_server import CompanionServer

CHAR_DIR = Path(__file__).resolve().parent.parent / "characters" / "default" / "campbell2"


async def test_sequence(server: CompanionServer):
    """Cycle through expressions to test compositing."""
    print("\n--- Test Sequence ---\n")
    expressions = server.compositor.expression_names

    for i, expr in enumerate(expressions):
        print(f"[{i+1}/{len(expressions)}] Expression: {expr}")
        server.anim.set_expression(expr)
        await asyncio.sleep(3)

    # Back to normal
    server.anim.set_expression("normal")
    print("\n--- Test Complete ---\n")


async def main():
    # Parse args
    audio_path = None
    test_mode = "--test" in sys.argv
    expression = "normal"

    for i, arg in enumerate(sys.argv):
        if arg == "--audio" and i + 1 < len(sys.argv):
            audio_path = sys.argv[i + 1]
        if arg == "--expression" and i + 1 < len(sys.argv):
            expression = sys.argv[i + 1]

    server = CompanionServer(CHAR_DIR)

    # Set initial expression
    server.anim.set_expression(expression)

    # Load audio if provided
    if audio_path:
        server.anim.load_audio(audio_path)
        server.anim.start_audio()

    if test_mode:
        # Start server + run test sequence
        server_task = asyncio.create_task(server.start())
        await asyncio.sleep(1)
        try:
            await test_sequence(server)
        finally:
            server_task.cancel()
    else:
        print(f"\nServer ready. Open renderer/index.html to connect.")
        print(f"Expressions: {server.compositor.expression_names}")
        print(f"Commands via WebSocket: set_expression, play_audio, stop_audio\n")
        await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
