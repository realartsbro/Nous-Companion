"""
Nous Companion — Hermes Observer

Watches the Hermes pipeline for state changes and emits events
to the companion server. Multiple observation strategies:

1. Session file watching — detects when conversation messages are added
2. Log tailing — watches gateway/agent logs for event patterns
3. Direct trigger — manual API for testing and integration
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Awaitable

logger = logging.getLogger(__name__)

# Event types the companion understands
EVENT_THINKING = "thinking"
EVENT_RESPONDING = "responding"
EVENT_COMPLETE = "complete"
EVENT_TOOL_USE = "tool_use"
EVENT_IDLE = "idle"
EVENT_SESSION_SWITCHED = "session_switched"
EVENT_SESSION_ENDED = "session_ended"

# A session is "live" if modified within this many seconds
LIVE_SESSION_CUTOFF_S = 30 * 60  # 30 minutes


class HermesObserver:
    """Watches Hermes state and emits companion events."""

    def __init__(
        self,
        hermes_home: Optional[str | Path] = None,
    ):
        self.hermes_home = Path(hermes_home or Path.home() / ".hermes")
        self.sessions_dir = self.hermes_home / "sessions"
        self.log_dir = self.hermes_home / "logs"

        # Callback: async function(event_type: str, context: dict) -> None
        self._callback: Optional[Callable[[str, dict], Awaitable[None]]] = None

        # State tracking  — PER-SESSION to survive session switching
        self._session_last_counts: dict[str, int] = {}   # filename → last known msg count
        self._session_last_mtimes: dict[str, float] = {} # filename → last known mtime
        self._current_session_file: Optional[Path] = None
        self._watched_session_id: Optional[str] = None
        self._is_running: bool = False
        self._task: Optional[asyncio.Task] = None

        # Session-switch cooldown: don't bounce between sessions too fast
        self._session_switch_cooldown: float = 3.0  # seconds
        self._last_session_switch_time: float = time.time()  # wall-clock, NOT file mtime

        # Ended-session cache (from state.db) — refreshed on demand
        self._ended_session_ids: set[str] = set()
        self._ended_cache_time: float = 0
        self._emitted_ended_for: set[str] = set()  # sessions we've already emitted EVENT_SESSION_ENDED for
        self._ENDED_CACHE_TTL: float = 10.0  # seconds
        self._session_meta_cache: dict[str, dict] = {}
        # ── Per-file stat cache ──
        self._debug_poll: bool = os.environ.get(
            "CODEC_DEBUG_POLL", ""
        ).strip().lower() in {"1", "true", "yes", "on"}

        # Defer the initial session inventory scan. On Windows builds pointed at
        # a WSL-backed Hermes home, eagerly parsing every session file here can
        # stall startup for tens of seconds before the websocket server is even
        # listening. The background poll loop will discover the active session
        # shortly after start without blocking the app bootstrap path.
        self._last_session_switch_time = 0.0

    # ── helpers ──────────────────────────────────────

    def _last_count(self) -> int:
        """Last known message count for the current session."""
        if not self._current_session_file:
            return 0
        return self._session_last_counts.get(self._current_session_file.name, 0)

    def _set_last_count(self, value: int):
        if self._current_session_file:
            self._session_last_counts[self._current_session_file.name] = value

    def _last_mtime(self) -> float:
        """Last known mtime for the current session."""
        if not self._current_session_file:
            return 0.0
        return self._session_last_mtimes.get(self._current_session_file.name, 0.0)

    def _set_last_mtime(self, value: float):
        if self._current_session_file:
            self._session_last_mtimes[self._current_session_file.name] = value

    @staticmethod
    def _read_session_json(path: Path) -> dict:
        """Read and parse a session JSON file (blocking I/O helper)."""
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _file_mtime(path: Optional[Path]) -> float:
        """Return a file's filesystem mtime, or 0 when unavailable."""
        if not path:
            return 0.0
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    @staticmethod
    def _record_for_path(inventory: list[dict], session_file: Optional[Path]) -> Optional[dict]:
        """Look up one cached inventory record by file path."""
        if not session_file:
            return None
        for record in inventory:
            if record["path"] == session_file:
                return record
        return None

    def _load_ended_sessions(self) -> set[str]:
        """Query state.db for sessions that have already ended."""
        ended: set[str] = set()
        db_path = self.hermes_home / "state.db"
        if not db_path.exists():
            return ended
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path), timeout=2.0)
            cur = conn.cursor()
            cur.execute("SELECT id FROM sessions WHERE ended_at IS NOT NULL")
            for row in cur.fetchall():
                ended.add(row[0])
            conn.close()
        except Exception:
            pass
        return ended

    def _trace_poll(self, message: str):
        """Emit poll diagnostics only when explicitly enabled."""
        if self._debug_poll:
            print(message, flush=True)

    def _get_ended_sessions(self) -> set[str]:
        """Return cached ended sessions, refreshing if stale."""
        import time as _time
        now = _time.time()
        if now - self._ended_cache_time < self._ENDED_CACHE_TTL:
            return self._ended_session_ids
        self._ended_session_ids = self._load_ended_sessions()
        self._ended_cache_time = now
        return self._ended_session_ids

    def _is_ended_session(self, data: dict) -> bool:
        """Check whether a session has ended according to state.db."""
        sid = data.get("session_id") or data.get("id")
        if not sid:
            return False
        return sid in self._get_ended_sessions()

    def _build_session_record(self, session_file: Path, data: dict, stat, ended_sessions: set[str]) -> dict:
        """Build cached session metadata from a loaded JSON document."""
        data_mtime = self._to_timestamp(data.get("last_updated"))
        effective_mtime = data_mtime or stat.st_mtime
        started_at = self._to_timestamp(data.get("started_at")) or data_mtime or stat.st_mtime
        session_id = data.get("session_id", session_file.stem)
        return {
            "path": session_file,
            "id": session_id,
            "file": session_file.name,
            "message_count": data.get("message_count", 0),
            "model": data.get("model", "?"),
            "started_at": started_at,
            "title": data.get("title") or self._guess_title(data),
            "fingerprint": self._session_fingerprint(data),
            "effective_mtime": effective_mtime,
            "is_companion": self._is_companion_session(data),
            "is_ended": session_id in ended_sessions,
            "is_curator": data.get("platform") == "curator",
            "source": data.get("platform", "") or "",
        }

    def _get_session_inventory(self) -> list[dict]:
        """Return cached metadata for all Hermes session files.

        The expensive JSON parse happens only when a session file's size or
        mtime changes; repeated list/auto-follow scans reuse cached metadata.
        """
        ended_sessions = self._get_ended_sessions()

        # ── Per-file stat cache ──
        # Reuse cached metadata for files whose (mtime_ns, size) hasn't changed.
        # The expensive JSON parse happens only when a session file's size or
        # mtime changes; repeated list/auto-follow scans reuse cached metadata.
        # The full glob+stat+parse is run in asyncio.to_thread() from callers
        # to keep it off the event loop.
        inventory: list[dict] = []
        seen_names: set[str] = set()

        session_files: list[tuple[Path, os.stat_result]] = []
        for session_file in self.sessions_dir.glob("session_*.json"):
            if session_file.name.startswith("session_api-"):
                continue
            try:
                stat = session_file.stat()
            except OSError:
                continue
            session_files.append((session_file, stat))

        session_files.sort(key=lambda item: item[1].st_mtime, reverse=True)

        for session_file, stat in session_files:
            seen_names.add(session_file.name)

            stat_key = (stat.st_mtime_ns, stat.st_size)
            cached = self._session_meta_cache.get(session_file.name)
            if cached and cached.get("stat_key") == stat_key:
                record = dict(cached["record"])
                record["is_ended"] = record.get("id") in ended_sessions
            else:
                try:
                    data = json.loads(session_file.read_text(encoding="utf-8"))
                except Exception:
                    continue
                record = self._build_session_record(session_file, data, stat, ended_sessions)
                self._session_meta_cache[session_file.name] = {
                    "stat_key": stat_key,
                    "record": dict(record),
                }
            inventory.append(record)
        # Clean stale cache entries
        stale = [name for name in self._session_meta_cache.keys() if name not in seen_names]
        for name in stale:
            self._session_meta_cache.pop(name, None)

        # Supplement with state.db sessions not found by file scan (gateway/telegram etc.)
        try:
            db_records = self._load_db_sessions(exclude_ids={r["id"] for r in inventory})
            inventory.extend(db_records)
        except Exception:
            pass

        return inventory

    def _load_db_sessions(self, exclude_ids: set[str]) -> list[dict]:
        """Query state.db for root sessions not found by file scan.

        Catches gateway sessions (Telegram, Discord, etc.) whose session
        files live under profile-specific directories. Returns records
        compatible with the file-scan inventory format.
        """
        db_path = self.hermes_home / "state.db"
        if not db_path.exists():
            return []

        profiles_dir = self.hermes_home / "profiles"
        import sqlite3

        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            if exclude_ids:
                placeholders = ",".join("?" for _ in exclude_ids)
                where_clause = f"AND s.id NOT IN ({placeholders})"
                params = list(exclude_ids)
            else:
                where_clause = ""
                params = []

            query = f"""
                SELECT s.id, s.source, s.model, s.title, s.started_at,
                       s.ended_at, s.message_count
                FROM sessions s
                WHERE s.parent_session_id IS NULL
                  AND s.source != 'tool'
                  {where_clause}
                ORDER BY s.started_at DESC
                LIMIT 50
            """
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()

        records: list[dict] = []
        for row in rows:
            sid = row["id"]
            source = row["source"] or "?"
            model = row["model"] or "?"
            title = row["title"] or ""
            mc = row["message_count"] or 0
            started = row["started_at"] or 0.0
            ended = row["ended_at"]

            # Find the session file — check default dir, then profile dirs
            session_file = self.sessions_dir / f"session_{sid}.json"
            if not session_file.exists() and profiles_dir.exists():
                found = False
                try:
                    for pdir in profiles_dir.iterdir():
                        if not pdir.is_dir():
                            continue
                        candidate = pdir / "sessions" / f"session_{sid}.json"
                        if candidate.exists():
                            session_file = candidate
                            found = True
                            break
                except OSError:
                    pass
                if not found:
                    continue  # skip if no file exists (can't watch)

            records.append({
                "path": session_file,
                "id": sid,
                "file": f"session_{sid}.json",
                "message_count": mc,
                "model": model,
                "started_at": started,
                "title": title,
                "fingerprint": sid,
                "effective_mtime": ended or started or 0.0,
                "is_companion": False,
                "is_ended": ended is not None,
                "is_curator": False,
            })
        return records

    # ── Public API ──────────────────────────────────────

    def on_event(self, callback: Callable[[str, dict], Awaitable[None]]):
        """Register an async callback for events."""
        self._callback = callback

    @staticmethod
    def _to_timestamp(value) -> float:
        """Convert various timestamp formats to Unix epoch seconds."""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # ISO 8601 string
            try:
                # Handle 'Z' suffix and microseconds
                s = value.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    # Naive datetime: Hermes writes local time without tz marker.
                    # Python's timestamp() assumes naive = local, which is correct.
                    # Do NOT force UTC — that creates a tz skew equal to the
                    # local offset (e.g. 7200s for CEST) and breaks mtime comparison.
                    pass
                return dt.timestamp()
            except Exception:
                pass
        return 0.0

    async def list_sessions(self, live_only: bool = True) -> list[dict]:
        """List available session files with metadata.

        By default only returns "live" sessions — those with recent conversation
        activity. Excludes API call sessions and deduplicates compression splits
        (multiple files from the same conversation are collapsed to the most
        recently active one).
        """
        raw_sessions: list[tuple[dict, float]] = []
        inventory = await asyncio.to_thread(self._get_session_inventory)
        for record in inventory:
            if record["is_companion"] or record["is_ended"] or record["is_curator"]:
                continue
            raw_sessions.append(({
                "id": record["id"],
                "file": record["file"],
                "message_count": record["message_count"],
                "model": record["model"],
                "started_at": record["started_at"],
                "title": record["title"],
                "source": record.get("source", "") or "",
                "_fingerprint": record["fingerprint"],
            }, record["effective_mtime"]))

        # Relative stale filter: skip sessions that are older than LIVE_SESSION_CUTOFF_S
        # from the MOST RECENT session. This is robust against WSL clock drift.
        if live_only and raw_sessions:
            max_mtime = max(mtime for _, mtime in raw_sessions)
            cutoff = max_mtime - LIVE_SESSION_CUTOFF_S
            raw_sessions = [(sess, mtime) for sess, mtime in raw_sessions if mtime >= cutoff]

        # Deduplicate: for each conversation fingerprint, keep only the most recently active session
        best_by_fp: dict[str, tuple[dict, float]] = {}
        for sess, mtime in raw_sessions:
            fp = sess.pop("_fingerprint")
            if fp not in best_by_fp or mtime > best_by_fp[fp][1]:
                best_by_fp[fp] = (sess, mtime)

        # Return sorted by most recent first
        return [sess for sess, _ in sorted(best_by_fp.values(), key=lambda x: x[1], reverse=True)]

    @staticmethod
    def _session_fingerprint(data: dict) -> str:
        """Return a stable fingerprint for a conversation.

        Sessions that are compression splits of the same conversation will
        share the same fingerprint (same first user message + same model).
        """
        msgs = data.get("messages", [])
        first_user = ""
        for m in msgs:
            if m.get("role") == "user":
                text = str(m.get("content", "")).strip()
                # Skip compaction markers
                if text and not text.startswith("[CONTEXT COMPACTION"):
                    first_user = text[:80]
                    break
        model = data.get("model", "?")
        return f"{model}::{first_user}"

    def watch_session(self, session_id: str) -> bool:
        """Switch to watching a specific session by ID or filename."""
        inventory = self._get_session_inventory()
        for record in inventory:
            if record["id"] == session_id or (record["path"] and record["path"].stem == session_id) or record["file"] == session_id:
                self._watched_session_id = record["id"]
                self._current_session_file = record["path"]
                self._set_last_count(record["message_count"])
                self._set_last_mtime(self._file_mtime(record["path"]))
                logger.info(f"Now watching session: {self._watched_session_id}")
                return True
        return False

    def unwatch(self):
        """Stop watching any specific session — go back to auto-follow latest."""
        self._watched_session_id = None
        self._find_active_session()
        logger.info("Unwatched — now auto-following latest session")

    async def get_current_context(self, max_messages: int = 6) -> list[dict]:
        """Read the last N messages from the watched session."""
        if not self._current_session_file or not self._current_session_file.exists():
            return []
        try:
            data = await asyncio.to_thread(self._read_session_json, self._current_session_file)
            messages = data.get("messages", [])
            return [{"role": m.get("role"), "content": str(m.get("content", ""))[:800]}
                    for m in messages[-max_messages:]]
        except Exception:
            return []

    def get_active_session_id(self) -> Optional[str]:
        """Return the currently active session id, including auto-follow mode."""
        if self._watched_session_id:
            return self._watched_session_id
        if not self._current_session_file:
            return None
        record = self._record_for_path(self._get_session_inventory(), self._current_session_file)
        if record:
            return record["id"]
        return self._current_session_file.stem

    async def start(self, poll_interval: float = 1.0):
        """Start the session watcher loop."""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._watch_loop(poll_interval))
        logger.info("HermesObserver started")

    async def stop(self):
        """Stop the watcher loop."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("HermesObserver stopped")

    # ─── Internal ────────────────────────────────────────────────

    def _find_active_session(self):
        """Find the most recently modified session file (excluding API call sessions
        and companion-internal quip-generation sessions)."""
        inventory = [r for r in self._get_session_inventory() if not r["is_companion"] and not r["is_ended"] and not r.get("is_curator")]
        now = time.time()
        max_mtime = max((record["effective_mtime"] for record in inventory), default=0.0)
        cutoff = (max_mtime - LIVE_SESSION_CUTOFF_S) if max_mtime else now - LIVE_SESSION_CUTOFF_S
        for record in sorted(inventory, key=lambda r: r["effective_mtime"], reverse=True):
            if record["effective_mtime"] < cutoff:
                continue
            self._current_session_file = record["path"]
            self._set_last_count(record["message_count"])
            self._set_last_mtime(self._file_mtime(record["path"]))
            logger.info(
                f"Auto-follow session: {record['file']} "
                f"({self._last_count()} messages)  "
                f"session_id={record['id']}"
            )
            return

    @staticmethod
    def _is_companion_session(data: dict) -> bool:
        """Detect sessions created by the companion's own LLM quip calls.

        These sessions contain the companion's personality prompt and
        'Available expressions:' marker. They are NOT user Hermes chats.
        """
        msgs = data.get("messages", [])
        for m in msgs:
            if m.get("role") == "system":
                content = str(m.get("content", ""))
                # Companion quips always include this marker
                if "Available expressions:" in content and "expression_name" in content:
                    return True
                # Also catch if the personality prompt is present with JSON format instruction
                if "{{\"quip\":" in content or "expression_name" in content:
                    return True
        return False

    @staticmethod
    def _guess_title(data: dict) -> str:
        """Extract a title from the first user message."""
        msgs = data.get("messages", [])
        for m in msgs:
            if m.get("role") == "user":
                text = str(m.get("content", "")).strip()
                if text:
                    return text[:40] + ("..." if len(text) > 40 else "")
        return "Untitled"

    async def _emit(self, event_type: str, context: dict):
        """Emit an event to the registered callback."""
        if self._callback:
            try:
                await self._callback(event_type, context)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

    async def _watch_loop(self, poll_interval: float):
        """Main watch loop — polls session file for changes."""
        while self._is_running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"Watch loop error: {e}")
            await asyncio.sleep(poll_interval)

    async def _poll_once(self):
        """Single poll iteration.

        Emits enriched events with conversation context so the companion
        understands *what* is happening, not just *which* tool was called.
        """
        import time as _time
        now = _time.time()

        # ── DEBUG: trace every poll ──
        self._trace_poll(
            f"[POLL] watched={self._watched_session_id}  file={self._current_session_file.name if self._current_session_file else None}  "
            f"last_count={self._last_count()}  last_mtime={self._last_mtime()}"
        )

        # ── Inventory scan at top so it runs once per poll ──
        # The per-file stat cache (in _get_session_inventory) prevents re-parsing
        # session files that haven't changed on disk.
        all_inventory = self._get_session_inventory()
        inventory: Optional[list[dict]] = None

        # Determine which session file to watch
        if self._watched_session_id:
            if not self._current_session_file or not self._current_session_file.exists():
                if not self.watch_session(self._watched_session_id):
                    logger.warning(f"Watched session {self._watched_session_id} gone, switching to auto")
                    self._watched_session_id = None
                    self._find_active_session()
        else:
            inventory = [r for r in all_inventory if not r["is_companion"] and not r["is_ended"]]
            if not inventory:
                self._trace_poll("[POLL] No session files found")
                return
            # Compute relative cutoff: within LIVE_SESSION_CUTOFF_S of the most recent session
            max_mtime = max((record["effective_mtime"] for record in inventory), default=0.0)
            cutoff = (max_mtime - LIVE_SESSION_CUTOFF_S) if max_mtime else now - LIVE_SESSION_CUTOFF_S
            current = None
            current_record = None
            for record in sorted(inventory, key=lambda r: r["effective_mtime"], reverse=True):
                if record["effective_mtime"] < cutoff:
                    continue
                current = record["path"]
                current_record = record
                break
            if current is None:
                self._trace_poll("[POLL] All recent sessions are companion/ended/stale")
                return
            if current != self._current_session_file:
                time_since_switch = now - self._last_session_switch_time
                # Only switch if cooldown elapsed AND current session has no new messages
                current_still_active = False
                if self._current_session_file and self._current_session_file.exists():
                    live_record = self._record_for_path(inventory, self._current_session_file)
                    if live_record:
                        current_msg_count = live_record["message_count"]
                        last_count = self._last_count()
                        # Session is "active" only if it has NEW messages since last poll
                        current_still_active = last_count > 0 and current_msg_count > last_count
                self._trace_poll(
                    f"[POLL] Considering switch: current={self._current_session_file.name if self._current_session_file else None}  "
                    f"candidate={current.name}  time_since_switch={time_since_switch:.1f}s  current_still_active={current_still_active}"
                )
                if time_since_switch >= self._session_switch_cooldown and not current_still_active:
                    self._trace_poll(f"[POLL] Switching to {current.name}")
                    self._current_session_file = current
                    self._last_session_switch_time = now
                    try:
                        data = json.loads(current.read_text())
                        # Only reset count if we've NEVER seen this session before
                        if current.name not in self._session_last_counts:
                            msgs = data.get("messages", [])
                            if msgs:
                                # Find the last user message so we don't skip it.
                                # If I've already started responding, the last message
                                # may be a tool result — we must still catch the prompt.
                                last_user_idx = 0
                                for i in range(len(msgs) - 1, -1, -1):
                                    if msgs[i].get("role") == "user":
                                        last_user_idx = i
                                        break
                                self._set_last_count(last_user_idx)
                                self._trace_poll(
                                    f"[POLL] First watch of {current.name}: starting from last user message "
                                    f"(idx {self._last_count()} of {len(msgs)})"
                                )
                            else:
                                self._set_last_count(0)
                        self._set_last_mtime(self._file_mtime(current))
                        await self._emit(EVENT_SESSION_SWITCHED, {
                            "session_id": data.get("session_id", current.stem),
                            "message_count": self._last_count(),
                            "model": data.get("model", ""),
                        })
                    except Exception:
                        pass
                    # DO NOT return here — continue to process messages from the switched-to session
                else:
                    self._trace_poll(
                        f"[POLL] Switch blocked: cooldown={time_since_switch:.1f}s  still_active={current_still_active}"
                    )

        if not self._current_session_file or not self._current_session_file.exists():
            self._trace_poll("[POLL] Current session file is gone")
            return

        # Check if the currently watched session has ended — if so, force a switch on next poll
        current_record = self._record_for_path(all_inventory, self._current_session_file)
        if current_record and current_record["is_ended"]:
            sid = current_record.get("id") or self._watched_session_id or ""
            if sid and sid not in self._emitted_ended_for:
                self._emitted_ended_for.add(sid)
                await self._emit(EVENT_SESSION_ENDED, {
                    "session_id": sid,
                    "message_count": current_record.get("message_count", 0),
                    "model": current_record.get("model", ""),
                })
            self._trace_poll(
                f"[POLL] Current session {self._current_session_file.name} has ENDED. Forcing switch on next poll."
            )
            self._last_session_switch_time = 0  # clear cooldown to force immediate switch
            self._set_last_mtime(0)  # clear mtime so next poll treats it as changed
            return

        current_mtime = self._file_mtime(self._current_session_file)
        self._trace_poll(
            f"[POLL] mtime check: current={current_mtime}  last={self._last_mtime()}  changed={current_mtime > self._last_mtime()}"
        )

        # Defensive: if stored reference is ahead of filesystem (clock drift,
        # timezone bug, or manual clock adjustment), reset to current so we
        # don't miss changes forever.
        if self._last_mtime() > current_mtime + 5:
            self._trace_poll(
                f"[POLL] last_mtime ahead of fs mtime by {self._last_mtime() - current_mtime:.1f}s - resetting"
            )
            self._set_last_mtime(current_mtime)

        if current_mtime <= self._last_mtime():
            return

        # NOTE: _set_last_mtime is deferred until after successful processing.
        # If json.load() fails (file mid-write), we must NOT update mtime,
        # otherwise the observer skips this file forever.

        try:
            data = await asyncio.to_thread(self._read_session_json, self._current_session_file)

            message_count = data.get("message_count", 0)
            messages = data.get("messages", [])
            self._trace_poll(
                f"[POLL] msg check: file_count={message_count}  len_msgs={len(messages)}  "
                f"last={self._last_count()}  new={message_count > self._last_count()}"
            )

            if message_count > self._last_count():
                new_msgs = messages[self._last_count():]
                self._trace_poll(
                    f"[POLL] Processing {len(new_msgs)} new messages (from idx {self._last_count()})"
                )
                # Keep track of the last user query and recent context
                # to enrich tool-use events with meaning
                for idx, msg in enumerate(new_msgs):
                    role = msg.get("role", "unknown")
                    content = str(msg.get("content", ""))[:800]
                    abs_idx = self._last_count() + idx
                    self._trace_poll(f"[POLL] New msg [{abs_idx}] role={role}  content_preview={content[:60]}...")

                    if role == "user":
                        # Find the last few messages for context
                        recent = messages[max(0, abs_idx-3):abs_idx+1]
                        ctx = self._build_context_summary(recent)
                        await self._emit(EVENT_THINKING, {
                            "query": content,
                            "context": ctx,
                            "session": self._current_session_file.stem,
                            "session_id": data.get("session_id", ""),
                            "message_count": message_count,
                        })

                    elif role == "assistant":
                        has_tool_calls = bool(msg.get("tool_calls"))
                        reasoning = (msg.get("reasoning") or msg.get("reasoning_content") or "")[:300]
                        if has_tool_calls:
                            # Enrich with: triggering user query + tool arguments
                            tc = msg.get("tool_calls", [])
                            tools = [t.get("function", {}).get("name", "?") for t in tc]
                            tool_args = []
                            for t in tc:
                                fn = t.get("function", {})
                                name = fn.get("name", "?")
                                args = fn.get("arguments", "")
                                try:
                                    parsed = json.loads(args) if args else {}
                                    summary = self._summarize_tool_args(name, parsed)
                                except Exception:
                                    summary = args[:60]
                                tool_args.append({"name": name, "summary": summary})

                            # Find the triggering user query (last user msg before this)
                            trigger_query = ""
                            for m in reversed(messages[:abs_idx]):
                                if m.get("role") == "user":
                                    trigger_query = str(m.get("content", ""))[:200]
                                    break

                            sig = self._score_tool_cluster(tool_args)
                            # Check for clarify tool calls (direct user input requests)
                            clarify_questions = []
                            for t in tc:
                                if t.get("function", {}).get("name") == "clarify":
                                    args = t.get("function", {}).get("arguments", "{}")
                                    try:
                                        parsed = json.loads(args) if args else {}
                                        q = parsed.get("question", "")
                                        if q:
                                            clarify_questions.append(q)
                                    except Exception:
                                        pass
                            # If assistant content itself asks for approval/input, also flag it
                            content_is_approval = self._is_approval_request(content) and len(content) < 300
                            approval_pending = bool(clarify_questions or content_is_approval)
                            if approval_pending:
                                sig = max(sig, 10)
                            await self._emit(EVENT_TOOL_USE, {
                                "tool_count": len(tc),
                                "tools": tools,
                                "tool_args": tool_args,
                                "trigger_query": trigger_query,
                                "assistant_reasoning": content[:400],
                                "reasoning": reasoning,
                                "session": self._current_session_file.stem,
                                "message_count": message_count,
                                "significance": sig,
                                "approval_pending": approval_pending,
                                "clarify_questions": clarify_questions,
                            })
                        else:
                            # Check if this "final response" is actually asking the user for something
                            content_is_approval = self._is_approval_request(content) and len(content) < 300
                            if content_is_approval:
                                # Treat as approval request instead of completion
                                trigger_query = ""
                                for m in reversed(messages[:abs_idx]):
                                    if m.get("role") == "user":
                                        trigger_query = str(m.get("content", ""))[:200]
                                        break
                                await self._emit(EVENT_TOOL_USE, {
                                    "tool_count": 0,
                                    "tools": [],
                                    "tool_args": [],
                                    "trigger_query": trigger_query,
                                    "assistant_reasoning": content[:400],
                                    "reasoning": reasoning,
                                    "session": self._current_session_file.stem,
                                    "message_count": message_count,
                                    "significance": 10,
                                    "approval_pending": True,
                                    "clarify_questions": [content[:300]],
                                })
                            else:
                                # Final text response
                                # Include a summary of what tools were used to get here
                                recent_tools = self._extract_recent_tool_chain(messages[:abs_idx])
                                await self._emit(EVENT_COMPLETE, {
                                    "response": content,
                                    "tool_chain": recent_tools,
                                    "session": self._current_session_file.stem,
                                    "session_id": data.get("session_id", ""),
                                    "message_count": message_count,
                                })

                    elif role == "tool":
                        # Try to link to the tool name via tool_call_id
                        tc_id = msg.get("tool_call_id", "")
                        tool_name = "?"
                        for m in reversed(messages[:abs_idx]):
                            if m.get("role") == "assistant" and m.get("tool_calls"):
                                for t in m.get("tool_calls", []):
                                    if t.get("id") == tc_id:
                                        tool_name = t.get("function", {}).get("name", "?")
                                        break
                                if tool_name != "?":
                                    break
                        result_text = content[:500]
                        is_approval = self._is_approval_request(result_text)
                        sig = 10 if is_approval else self._score_tool_significance(tool_name, {}, result_text)
                        await self._emit(EVENT_TOOL_USE, {
                            "tool_result": content[:200],
                            "tool_name": tool_name,
                            "session": self._current_session_file.stem,
                            "message_count": message_count,
                            "significance": sig,
                            "approval_pending": is_approval,
                        })

                self._set_last_count(message_count)

            # Update mtime reference on every successful read so that mtime-only
            # changes (compaction, state updates) don't keep the session looking
            # "active" and blocking switches forever.
            self._set_last_mtime(current_mtime)

        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Session read error: {e}")
            self._trace_poll(f"[POLL] Session read error (will retry): {e}")

        except Exception as e:
            logger.error(f"Unexpected poll error: {e}")
            self._trace_poll(f"[POLL] Unexpected error: {e}")

    @staticmethod
    def _build_context_summary(messages: list[dict]) -> str:
        """Build a brief summary of recent conversation for context."""
        parts = []
        for m in messages:
            role = m.get("role", "?")
            text = str(m.get("content", ""))[:120].replace("\n", " ")
            if text:
                parts.append(f"{role}: {text}")
        return " | ".join(parts)

    @staticmethod
    def _summarize_tool_args(tool_name: str, args: dict) -> str:
        """Create a human-readable summary of what a tool is doing."""
        if not args:
            return ""
        # Terminal / shell
        if tool_name in ("terminal", "shell", "bash") and "command" in args:
            cmd = args["command"]
            # Strip long paths for brevity
            cmd = cmd.replace(str(Path.home()), "~")
            return f"command: {cmd[:80]}"
        # File read
        if tool_name in ("read_file", "file_read") and "path" in args:
            return f"reading {args['path']}"
        # File write
        if tool_name in ("write_file", "file_write") and "path" in args:
            return f"writing {args['path']}"
        # Web search
        if tool_name in ("web_search", "search") and "query" in args:
            return f"searching: {args['query'][:60]}"
        # Browser
        if tool_name in ("browser_navigate", "browser") and "url" in args:
            return f"opening {args['url'][:60]}"
        # Generic: show first arg
        first_k = list(args.keys())[:2]
        pairs = [f"{k}={str(args[k])[:30]}" for k in first_k]
        return ", ".join(pairs)

    # ─── Significance scoring ─────────────────────────────────────────

    # Tools that are just noise — polling, logging, snapshots, etc.
    _NOISY_TOOLS = frozenset({
        "process", "browser_snapshot", "browser_click", "browser_scroll",
        "browser_press", "browser_console", "browser_get_images",
        "browser_vision", "browser_navigate",  # navigate is often just a step
    })

    # Tools that are always interesting — user-visible actions
    _ACTION_TOOLS = frozenset({
        "terminal", "shell", "execute_code", "delegate_task",
        "web_search", "search", "web_extract",
        "write_file", "patch", "file_write",
    })

    # File patterns that are low-significance (cache, config, temp)
    _LOW_SIG_PATHS = re.compile(
        r"/(tmp|temp|cache|\.cache|\.hermes/logs|__pycache__|\.git)/|"
        r"\.(log|tmp|cache|pyc)$|"
        r"/session_\d{8}_\d{6}.*\.json$|"
        r"config\.ya?ml$|settings\.json$",
        re.I,
    )

    @classmethod
    def _score_tool_significance(cls, tool_name: str, args: dict, result_text: str = "") -> int:
        """Score a tool event 0–10. Higher = more worthy of a vocal reaction.

        0  = noise (poll, log read, empty tools)
        2  = low-value file/config access
        4  = routine file read on project code
        5  = search, browser extract
        6  = write/patch to project files
        7  = execute_code, delegate_task, actual terminal commands
        8  = destructive/dangerous command (rm, delete, format)
        10 = approval request detected
        """
        # ── Approval request detection (highest priority) ──
        if result_text and cls._is_approval_request(result_text):
            return 10

        # ── Empty/no-op tools ──
        if not tool_name or tool_name == "?":
            return 0

        # ── Known noisy tools ──
        if tool_name in cls._NOISY_TOOLS:
            # Even noisy tools might be significant if args say otherwise
            cmd = args.get("command", "") if isinstance(args, dict) else ""
            if tool_name == "process" and isinstance(cmd, str):
                # process(poll), process(log), process(list) = noise
                if any(x in cmd for x in ("poll", "log", "list", "status", "ps ")):
                    return 0
                # process(kill) on companion = noise
                if "companion" in cmd or "codec" in cmd:
                    return 1
            if tool_name in ("browser_navigate", "browser_snapshot"):
                return 1
            return 2

        # ── File reads ──
        if tool_name in ("read_file", "file_read"):
            path = args.get("path", "") if isinstance(args, dict) else ""
            if cls._LOW_SIG_PATHS.search(str(path)):
                return 2
            return 4

        # ── File writes ──
        if tool_name in ("write_file", "patch", "file_write"):
            path = args.get("path", "") if isinstance(args, dict) else ""
            if cls._LOW_SIG_PATHS.search(str(path)):
                return 3
            return 6

        # ── Search / browse ──
        if tool_name in ("web_search", "search"):
            return 5
        if tool_name == "web_extract":
            return 5

        # ── Code execution ──
        if tool_name in ("execute_code", "delegate_task"):
            return 7

        # ── Terminal / shell ──
        if tool_name in ("terminal", "shell", "bash"):
            cmd = args.get("command", "") if isinstance(args, dict) else ""
            cmd = str(cmd).lower()
            # Destructive commands get higher score
            destructive = ("rm -rf", "rm -r", "del ", "format", "dd if=", "mkfs",
                           ":(){ :|:& };:", "> /dev/", "drop database", "drop table")
            if any(d in cmd for d in destructive):
                return 8
            # Writing/modifying commands
            if any(c in cmd for c in ("git push", "git reset", "git clean", "docker ", "deploy", "build")):
                return 6
            # Reading/listing commands are lower
            if any(c in cmd for c in ("cat ", "ls ", "head ", "tail ", "grep ", "find ", "echo ")):
                return 3
            return 7

        # ── Default ──
        return 4

    _APPROVAL_KEYWORDS = re.compile(
        r"(requires? (user )?approval|waiting for approval|"
        r"approve\?|do you approve|asking (for |)your approval|needs? your approval|"
        r"needs? (your )?confirmation|confirmation (is )?(needed|required)|y/n|yes/no|proceed\?|"
        r"this command requires|dangerous command|destructive operation|"
        r"permanently delete|are you sure|shall i proceed|"
        r"please confirm|can you confirm|your input (is )?needed|waiting for your|"
        r"need your (input|confirmation|approval))",
        re.I,
    )

    @classmethod
    def _is_approval_request(cls, text: str) -> bool:
        """Detect if a tool result or message is an approval request."""
        if not text:
            return False
        return bool(cls._APPROVAL_KEYWORDS.search(text[:500]))

    @classmethod
    def _score_tool_cluster(cls, tool_args: list[dict], result_text: str = "") -> int:
        """Score a cluster of tool calls — returns the MAX significance."""
        max_score = 0
        for ta in tool_args:
            name = ta.get("name", "?")
            # Parse summary back into rough args for scoring
            summary = ta.get("summary", "")
            args = {}
            if "command:" in summary:
                args["command"] = summary.split("command:", 1)[1].strip()
            elif "reading " in summary:
                args["path"] = summary.split("reading ", 1)[1].strip()
            elif "writing " in summary:
                args["path"] = summary.split("writing ", 1)[1].strip()
            elif "searching:" in summary:
                args["query"] = summary.split("searching:", 1)[1].strip()
            score = cls._score_tool_significance(name, args, result_text)
            max_score = max(max_score, score)
        return max_score

    @staticmethod
    def _extract_recent_tool_chain(messages: list[dict]) -> list[dict]:
        """Extract the chain of recent tool calls + results before a response."""
        chain = []
        # Look backward from the end for the last assistant message with tool_calls
        for m in reversed(messages):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for t in m.get("tool_calls", []):
                    fn = t.get("function", {})
                    chain.append({
                        "name": fn.get("name", "?"),
                        "summary": HermesObserver._summarize_tool_args(
                            fn.get("name", ""),
                            json.loads(fn.get("arguments", "{}")) if fn.get("arguments") else {}
                        ),
                    })
                break
        return list(reversed(chain))

    # ─── Legacy log watcher (kept for compatibility) ──────────────────

    async def watch_logs(self, poll_interval: float = 2.0):
        """
        Watch gateway/agent logs for event patterns.
        Detects model calls, tool use, and completion events.
        """
        log_file = self.log_dir / "agent.log"
        if not log_file.exists():
            logger.warning(f"Agent log not found: {log_file}")
            return

        logger.info(f"Log watcher started: {log_file}")

        # Start from end of file
        pos = log_file.stat().st_size

        # Patterns to detect
        patterns = {
            EVENT_THINKING: [
                re.compile(r"Calling model|LLM request|Starting completion", re.I),
            ],
            EVENT_TOOL_USE: [
                re.compile(r"Tool call|function_call|handle_function", re.I),
            ],
            EVENT_COMPLETE: [
                re.compile(r"Response complete|Final response|Text response", re.I),
            ],
        }

        while True:
            try:
                current_size = log_file.stat().st_size
                if current_size > pos:
                    with open(log_file) as f:
                        f.seek(pos)
                        new_lines = f.readlines()
                    pos = current_size

                    for line in new_lines:
                        for event_type, pats in patterns.items():
                            for pat in pats:
                                if pat.search(line):
                                    await self._emit(event_type, {
                                        "source": "log",
                                        "line": line.strip()[:200],
                                    })
                                    break

            except Exception as e:
                logger.error(f"Log watcher error: {e}")

            await asyncio.sleep(poll_interval)

    # ─── Direct API (for manual triggers and testing) ───────────

    async def trigger_thinking(self, query: str = ""):
        """Manually trigger a thinking event."""
        await self._emit(EVENT_THINKING, {"query": query, "source": "manual"})

    async def trigger_responding(self, text: str = ""):
        """Manually trigger a responding event."""
        await self._emit(EVENT_RESPONDING, {"text": text, "source": "manual"})

    async def trigger_complete(self, response: str = ""):
        """Manually trigger a completion event."""
        await self._emit(EVENT_COMPLETE, {"response": response, "source": "manual"})

    async def trigger_tool_use(self, tool_name: str = ""):
        """Manually trigger a tool use event."""
        await self._emit(EVENT_TOOL_USE, {"tool_name": tool_name, "source": "manual"})

    async def trigger_idle(self):
        """Manually trigger idle state."""
        await self._emit(EVENT_IDLE, {"source": "manual"})
