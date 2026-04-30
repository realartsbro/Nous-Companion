#!/usr/bin/env python3
"""Launch Nous Companion with repo-relative defaults."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


# Normalize __file__ to handle Windows \\?\ long-path prefix
# which Python pathlib does not resolve correctly.
_script_file = os.path.abspath(__file__)
REPO_ROOT = Path(_script_file).resolve().parent.parent
# Prefer source tree (development) over bundled (release) so Python edits
# take effect without needing to rebuild the Tauri binary.
# From bundle:  REPO_ROOT = .../target/release/
# From source:  REPO_ROOT = .../project/
for candidate in [
    REPO_ROOT.parent.parent.parent / "src",  # from bundle → project root /src
    REPO_ROOT / "src",                        # from source → project root /src
]:
    if (candidate / "server" / "companion_server.py").exists():
        SRC_ROOT = candidate.resolve()
        break
else:
    SRC_ROOT = (REPO_ROOT / "src").resolve()
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from server.companion_server import CompanionServer  # noqa: E402

_RENDERER_DIR = REPO_ROOT / "renderer"


def _start_http_server(host: str, http_port: int) -> None:
    """Start a minimal HTTP server for the renderer in a background thread."""
    import http.server
    import threading

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(_RENDERER_DIR), **kwargs)

        def log_message(self, fmt, *args):
            pass  # suppress request logs — the WS server handles logging

    server = http.server.HTTPServer((host, http_port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[HTTP] Renderer available at http://{host}:{http_port}", flush=True)


def default_character_dir() -> Path:
    for candidate in (
        REPO_ROOT / "characters" / "nous",
        REPO_ROOT / "characters" / "default",
    ):
        if candidate.exists():
            return candidate
    return REPO_ROOT / "characters"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Nous Companion")
    parser.add_argument(
        "--character-dir",
        default=str(default_character_dir()),
        help="Path to the character directory to load on startup",
    )
    parser.add_argument(
        "--hermes-home",
        default=None,
        help="Path to Hermes home (defaults to HERMES_HOME or ~/.hermes)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="WebSocket bind host")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket port")
    parser.add_argument("--http-port", type=int, default=8766, help="HTTP port for browser access (0 = disable)")
    parser.add_argument("--fps", type=int, default=30, help="Animation frame rate")
    args = parser.parse_args()

    if args.http_port:
        _start_http_server(args.host, args.http_port)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    server = CompanionServer(
        character_dir=args.character_dir,
        hermes_home=args.hermes_home,
        host=args.host,
        ws_port=args.port,
        fps=args.fps,
    )
    server.run()


if __name__ == "__main__":
    main()
