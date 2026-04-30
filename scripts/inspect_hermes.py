"""Inspect Hermes session data to understand the event format."""

import json
from pathlib import Path

SESSIONS_FILE = Path.home() / ".hermes" / "sessions" / "sessions.json"
SESSION_DIR = Path.home() / ".hermes" / "sessions"

print("=== sessions.json ===")
with open(SESSIONS_FILE) as f:
    data = json.load(f)

if isinstance(data, list):
    print(f"Type: list, {len(data)} entries")
    for s in data[-2:]:
        print(json.dumps(s, indent=2)[:600])
        print("---")
elif isinstance(data, dict):
    print(f"Type: dict, {len(data)} keys")
    for k in list(data.keys())[-2:]:
        print(f"{k}: {json.dumps(data[k], indent=2)[:500]}")
        print("---")

# Check one session file
session_files = sorted(SESSION_DIR.glob("session_*.json"))
if session_files:
    print(f"\n=== Latest session file: {session_files[-1].name} ===")
    with open(session_files[-1]) as f:
        session = json.load(f)
    print(f"Type: {type(session).__name__}")
    if isinstance(session, list):
        print(f"Messages: {len(session)}")
        for msg in session[-3:]:
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))[:200]
            print(f"  [{role}] {content}")
    elif isinstance(session, dict):
        print(f"Keys: {list(session.keys())[:10]}")
        for k, v in list(session.items())[:5]:
            print(f"  {k}: {str(v)[:200]}")
