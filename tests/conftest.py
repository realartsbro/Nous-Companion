"""
Test harness for WebSocket integration tests against the Nous Companion server.

Provides fixtures that:
  1. Start a CompanionServer on a random high port
  2. Use temp directories for character data and Hermes home
  3. Connect via WebSocket as a control client
  4. Collect and query server messages

Diagnostic flags suppress the Hermes observer, frame streaming, and session
refresh so the test server does not depend on a real Hermes installation.
"""

import asyncio
import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio
import websockets

# Ensure the src/ directory is on the Python path (same pattern as other tests)
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ═══════════════════════════════════════════════════════════════════════════
# Environment helpers
# ═══════════════════════════════════════════════════════════════════════════

# Save original env so we can restore after tests
_SAVED_ENV: dict[str, Optional[str]] = {}


def _set_diag_env():
    """Set diagnostic env vars to disable features needing real infrastructure."""
    for key in [
        "CODEC_DIAG_DISABLE_OBSERVER",
        "CODEC_DIAG_DISABLE_FRAME_STREAM",
        "CODEC_DIAG_DISABLE_ALL_RENDERER_FRAMES",
        "CODEC_DIAG_DISABLE_SESSION_REFRESH",
    ]:
        _SAVED_ENV[key] = os.environ.get(key)
        os.environ[key] = "1"


def _restore_env():
    """Restore environment to pre-test state."""
    for key, saved in _SAVED_ENV.items():
        if saved is not None:
            os.environ[key] = saved
        else:
            os.environ.pop(key, None)


# Set diagnostic env IMMEDIATELY so imports of companion_server see them
_set_diag_env()


# ═══════════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════════

def find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _project_root() -> Path:
    """Return the repository root (parent of tests/)."""
    return Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════════════════
# Test server harness
# ═══════════════════════════════════════════════════════════════════════════

class CompanionTestServer:
    """Manages a CompanionServer instance for integration testing.

    Starts the server on a random high port with temp Hermes home and character
    data.  The server is run as a background asyncio task.
    """

    def __init__(
        self,
        characters_dir: Path,
        hermes_home: Path,
        port: int,
    ):
        self.characters_dir = characters_dir
        self.hermes_home = hermes_home
        self.port = port
        self.server = None
        self._server_task: Optional[asyncio.Task] = None
        self._ready_path: Optional[Path] = None

    async def start(self) -> None:
        """Start the companion server in a background task and wait for readiness."""
        from server.companion_server import CompanionServer

        # Find a usable character directory (must have config.yaml + sprites)
        char_dirs = sorted(
            d
            for d in self.characters_dir.iterdir()
            if d.is_dir()
            and (d / "config.yaml").exists()
            and not d.name.startswith(".")
        )
        if not char_dirs:
            raise RuntimeError(
                f"No character directories found in {self.characters_dir}"
            )

        char_dir = str(char_dirs[0])

        # Create a ready-file path and set env so the server writes it
        self._ready_path = (
            self.hermes_home / ".companion_test_ready"
        )
        os.environ["NOUS_COMPANION_READY_FILE"] = str(self._ready_path)
        # Remove stale marker
        self._ready_path.unlink(missing_ok=True)

        self.server = CompanionServer(
            character_dir=char_dir,
            host="127.0.0.1",
            ws_port=self.port,
            hermes_home=str(self.hermes_home),
        )

        self._server_task = asyncio.create_task(self.server.start())

        # Poll for readiness marker
        for _ in range(80):  # 8 seconds max
            if self._ready_path.exists():
                return
            await asyncio.sleep(0.1)

        raise RuntimeError(
            f"Server did not become ready on port {self.port} "
            f"(no ready marker at {self._ready_path})"
        )

    async def stop(self) -> None:
        """Cancel the server task and clean up."""
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._server_task = None
        self.server = None
        # Clean up ready marker
        if self._ready_path:
            self._ready_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# WebSocket client helper
# ═══════════════════════════════════════════════════════════════════════════

class CompanionWSClient:
    """WebSocket client connected to a companion test server.

    Registers as a ``control`` client (settings UI) and collects every message
    in a background task so tests can inspect the full message history.
    """

    def __init__(self, port: int, role: str = "control"):
        self.port = port
        self.role = role
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._collected: list[dict] = []
        self._collector_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Connect and register as a client with the configured role."""
        self.ws = await websockets.connect(f"ws://127.0.0.1:{self.port}")
        # Register with the configured role so we get broadcasts for that role
        await self.ws.send(
            json.dumps({"cmd": "register_client", "role": self.role})
        )
        # Start background message collector
        self._collected = []
        self._collector_task = asyncio.create_task(self._collect_messages())

    async def _collect_messages(self) -> None:
        """Background task: collect every incoming message."""
        try:
            while True:
                msg = await self.ws.recv()
                try:
                    self._collected.append(json.loads(msg))
                except json.JSONDecodeError:
                    pass
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        if self._collector_task:
            self._collector_task.cancel()
            try:
                await self._collector_task
            except asyncio.CancelledError:
                pass
            self._collector_task = None
        if self.ws:
            await self.ws.close()
            self.ws = None

    # ── send ───────────────────────────────────────────────────────────

    async def send(self, data: dict) -> None:
        """Send a JSON command to the server."""
        await self.ws.send(json.dumps(data))

    # ── waiting / querying ─────────────────────────────────────────────

    async def wait_for(
        self, msg_type: str, timeout: float = 5.0
    ) -> dict:
        """Block until a message with ``type == msg_type`` arrives.

        Returns the *first* matching message (removing it from the collector).
        Raises ``TimeoutError`` if not seen within *timeout* seconds.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            for i, msg in enumerate(self._collected):
                if msg.get("type") == msg_type:
                    return self._collected.pop(i)
            await asyncio.sleep(0.05)
        raise TimeoutError(
            f"Timeout waiting for message type '{msg_type}' "
            f"(collected {len(self._collected)} msgs: "
            f"{[m.get('type') for m in self._collected[-20:]]})"
        )

    def has_type(self, msg_type: str) -> bool:
        """Return True if *any* collected message has the given type."""
        return any(msg.get("type") == msg_type for msg in self._collected)

    def get_all_of_type(self, msg_type: str) -> list[dict]:
        """Return (and remove) every collected message of the given type."""
        result = [
            msg for msg in self._collected if msg.get("type") == msg_type
        ]
        self._collected = [
            msg for msg in self._collected if msg.get("type") != msg_type
        ]
        return result

    @property
    def collected(self) -> list[dict]:
        """A snapshot copy of currently collected messages."""
        return list(self._collected)

    def clear(self) -> None:
        """Discard all collected messages."""
        self._collected.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Pytest fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def test_server():
    """Yield a running ``CompanionTestServer`` with temp directories.

    The server uses:
    * A copy of the real ``characters/`` directory (needs sprite files).
    * A fresh temp Hermes home so no real profiles/sessions are touched.
    * A random high port to avoid port conflicts.
    """
    tmp = Path(tempfile.mkdtemp(prefix="nous_companion_test_"))
    chars_tmp = tmp / "characters"
    hermes_tmp = tmp / "hermes"

    hermes_tmp.mkdir(parents=True)

    # Copy characters so we don't mutate the real ones
    shutil.copytree(
        _project_root() / "characters",
        chars_tmp,
        symlinks=False,
        ignore=shutil.ignore_patterns(".git*", "__pycache__", "*.pyc"),
    )

    port = find_free_port()
    server = CompanionTestServer(chars_tmp, hermes_tmp, port)
    await server.start()

    yield server

    await server.stop()
    shutil.rmtree(str(tmp), ignore_errors=True)


@pytest_asyncio.fixture
async def companion_ws(test_server):
    """Yield a connected ``CompanionWSClient`` for the running test server."""
    client = CompanionWSClient(test_server.port)
    await client.connect()
    yield client
    await client.disconnect()
