"""
Companion Recorder — pluggable JSON Lines event recorder.

Captures all companion inputs, outputs, and state changes into
JSON Lines files matching the approved RECORDING-SCHEMA.md (v5).

Design principles:
- Non-blocking: all file I/O is offloaded to a background writer thread
- Pluggable: attaches via method wrapping, server needs minimal changes
- Crash-safe: JSON Lines format survives unexpected termination
- Audio stored externally: SHA-256 hashed cache files, never inline
"""

import base64
import hashlib
import json
import logging
import queue
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("nous_companion.recorder")

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

RECORDINGS_DIR_NAME = "recordings"
AUDIO_CACHE_DIR_NAME = "audio_cache"
RECORDING_VERSION = "1.0.0"
RECORDING_FORMAT_VERSION = 1

# Broadcast type → recording event type mapping
BROADCAST_TO_RECORDING: dict[str, str] = {
    "status":                   "output_status",
    "text":                     "output_text",
    "audio_stop":               "output_audio_stop",
    "character_switched":       "output_character_switched",
    "character_switch_rejected":"output_character_switch_rejected",
    "profile_changed":          "output_profile_changed",
    "model_changed":            "system_model_changed",
    "tts_engine_changed":       "system_tts_engine_changed",
    "godmode_changed":          "system_godmode_changed",
    "character_created":        "system_character_changed",
    "character_deleted":        "system_character_changed",
    "character_saved":          "system_character_changed",
    "character_exported":       "system_character_changed",
    "character_imported":       "system_character_changed",
    "profile_switch_result":    "system_profile_switch_result",
    "scene_loaded":             "output_scene_loaded",
    "scene_cue":                "output_scene_cue",
    "scene_overlay":            "output_scene_overlay",
    "scene_complete":           "output_scene_complete",
    "scene_error":              "output_scene_error",
}

# Broadcast types that carry character change info and need special handling
CHARACTER_CHANGE_BROADCASTS = {
    "character_created", "character_deleted", "character_saved",
    "character_exported", "character_imported",
}

# Broadcast types that carry scene player results
SCENE_RESULT_BROADCASTS = {
    "play_scene_result":    "output_scene_started",
    "pause_scene_result":   "output_scene_paused",
    "stop_scene_result":    "output_scene_stopped",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helper: SHA-256 hashing
# ──────────────────────────────────────────────────────────────────────────────

def sha256_hex(data: bytes) -> str:
    """Return lowercase hex SHA-256 digest of data."""
    return hashlib.sha256(data).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# CompanionRecorder
# ──────────────────────────────────────────────────────────────────────────────

class CompanionRecorder:
    """Pluggable recorder that captures companion events as JSON Lines.

    Usage:
        recorder = CompanionRecorder(server)
        recorder.start(reason="auto")
        ... companion runs ...
        recorder.stop()
    """

    def __init__(self, server: "CompanionServer"):  # type: ignore[name-defined]
        self._server = server
        self._hermes_home: Path = server.hermes_home

        # ── Recording state ────────────────────────────────────────────────
        self._recording: bool = False
        self._seq: int = 0
        self._start_time_ns: int = 0

        # ── File / writer ──────────────────────────────────────────────────
        self._file_path: Optional[Path] = None
        self._file_handle: Any = None   # io.TextIOWrapper
        self._write_queue: queue.Queue = queue.Queue(maxsize=10000)
        self._writer_thread: Optional[threading.Thread] = None
        self._writer_running: threading.Event = threading.Event()

        # ── Audio cache ────────────────────────────────────────────────────
        self._recordings_dir: Path = self._hermes_home / RECORDINGS_DIR_NAME
        self._audio_cache_dir: Path = self._recordings_dir / AUDIO_CACHE_DIR_NAME

        # ── Original server methods (for unhooking) ────────────────────────
        self._orig_broadcast = None
        self._orig_broadcast_audio = None
        self._orig_on_hermes_event = None

        # ── Tracking state ─────────────────────────────────────────────────
        self._last_session_id: Optional[str] = None
        self._last_quip_seq: Optional[int] = None
        self._last_trigger_event_seq: Optional[int] = None
        self._last_expression: str = "normal"
        self._pending_quip: Optional[dict] = None  # quip metadata awaiting audio
        self._frame_count: int = 0
        self._last_frame_time_ns: int = 0
        self._frame_throttle_ns: int = 2_000_000_000  # 2s minimum between frame records
        self._seen_hashes: set = set()  # dedup audio cache writes
        self._audio_seq_to_meta: dict[int, dict] = {}  # reaction_seq -> audio meta

        # ── Metadata fields (populated at start) ───────────────────────────
        self._recording_id: str = ""
        self._recording_start_utc: str = ""

    # ────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ────────────────────────────────────────────────────────────────────────

    def start(self, reason: str = "auto") -> bool:
        """Start recording. Returns True if recording started successfully."""
        if self._recording:
            logger.warning("Recorder already running")
            return False

        try:
            self._recordings_dir.mkdir(parents=True, exist_ok=True)
            self._audio_cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Cannot create recording directories: {e}")
            return False

        # ── Determine file path ────────────────────────────────────────────
        from hermes_runtime import hermes_path
        now = datetime.now(timezone.utc)
        self._recording_start_utc = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        iso_short = now.strftime("%Y-%m-%dT%H%M%SZ")

        profile = getattr(self._server, "_active_profile", "default") or "default"
        session_id = ""
        try:
            session_id = self._server.observer._watched_session_id or ""
        except Exception:
            pass
        session_short = session_id[:8] if session_id else "nosession"
        character = ""
        try:
            character = getattr(self._server.char_manager, "active_id", "") or ""
        except Exception:
            pass
        character = character or "unknown"

        filename = f"{profile}_{session_short}_{character}_{iso_short}.jsonl"
        self._file_path = self._recordings_dir / filename

        # ── Open file ──────────────────────────────────────────────────────
        try:
            self._file_handle = open(str(self._file_path), "w", encoding="utf-8")
        except OSError as e:
            logger.error(f"Cannot open recording file {self._file_path}: {e}")
            return False

        # ── Start writer thread ────────────────────────────────────────────
        self._writer_running.set()
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            daemon=True,
            name="companion-recorder-writer",
        )
        self._writer_thread.start()

        # ── Reset state ────────────────────────────────────────────────────
        self._seq = 0
        self._start_time_ns = time.monotonic_ns()
        self._frame_count = 0
        self._last_frame_time_ns = 0

        # ── Build recording ID ─────────────────────────────────────────────
        self._recording_id = f"rec_{now.strftime('%Y%m%d_%H%M%S')}_{profile}_{character}"

        # ── Write metadata header ──────────────────────────────────────────
        self._write_metadata_header(reason, now, session_id, session_short, profile, character)

        # ── Hook into server ───────────────────────────────────────────────
        self._hook_server()

        # ── Record start event ─────────────────────────────────────────────
        self._record_recording_control("start", reason)

        self._recording = True
        logger.info(f"Recording started: {self._file_path}")
        return True

    def stop(self, reason: str = "shutdown") -> None:
        """Stop recording and clean up."""
        if not self._recording:
            return

        # ── Record stop event ──────────────────────────────────────────────
        self._record_recording_control("stop", reason)

        # ── Unhook from server ─────────────────────────────────────────────
        self._unhook_server()

        # ── Drain the write queue ──────────────────────────────────────────
        self._drain_queue(timeout=3.0)

        # ── Stop writer ────────────────────────────────────────────────────
        self._writer_running.clear()
        # Push sentinel to wake the writer thread
        try:
            self._write_queue.put_nowait(None)
        except queue.Full:
            pass

        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=5.0)

        # ── Close file ─────────────────────────────────────────────────────
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None

        self._recording = False
        logger.info(f"Recording stopped: {self._file_path} ({self._seq} events)")

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def recording_path(self) -> Optional[Path]:
        return self._file_path

    # ────────────────────────────────────────────────────────────────────────
    # Writer thread
    # ────────────────────────────────────────────────────────────────────────

    def _writer_loop(self) -> None:
        """Background thread: pull JSON strings from queue and write them."""
        while self._writer_running.is_set():
            try:
                item = self._write_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is None:  # sentinel
                break

            if self._file_handle:
                try:
                    self._file_handle.write(item)
                    self._file_handle.write("\n")
                    self._file_handle.flush()
                except Exception as e:
                    logger.error(f"Recorder write error: {e}")

    def _enqueue(self, event: dict) -> None:
        """Serialize and enqueue an event for writing. Thread-safe."""
        try:
            line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            logger.error(f"Recorder JSON serialize error: {e}")
            return

        try:
            self._write_queue.put_nowait(line)
        except queue.Full:
            logger.warning("Recorder write queue full — dropping event")

    def _drain_queue(self, timeout: float = 3.0) -> int:
        """Drain the write queue by processing all pending items in the writer thread.
        Returns the number of items drained."""
        drained = 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                item = self._write_queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                break
            if self._file_handle:
                try:
                    self._file_handle.write(item)
                    self._file_handle.write("\n")
                    self._file_handle.flush()
                    drained += 1
                except Exception as e:
                    logger.error(f"Recorder drain write error: {e}")
                    break
        return drained

    # ────────────────────────────────────────────────────────────────────────
    # Core recording method
    # ────────────────────────────────────────────────────────────────────────

    def _record(self, rec_type: str, **fields: Any) -> int:
        """Record a single event. Returns the event's seq number."""
        if not self._recording:
            return -1

        seq = self._seq
        self._seq += 1
        wall_ts_ms = int((time.monotonic_ns() - self._start_time_ns) / 1_000_000)

        event = {
            "seq": seq,
            "wall_ts_ms": wall_ts_ms,
            "type": rec_type,
            **fields,
        }
        self._enqueue(event)
        return seq

    # ────────────────────────────────────────────────────────────────────────
    # Metadata header
    # ────────────────────────────────────────────────────────────────────────

    def _write_metadata_header(
        self, reason: str, now: datetime,
        session_id: str, session_short: str,
        profile: str, character: str,
    ) -> None:
        """Write the metadata header as the first JSON line."""
        server = self._server

        # Gather companion config
        settings = getattr(server, "settings", {})
        char = getattr(server.char_manager, "active", None)
        brain_prompt = getattr(server, "_brain_prompt", "")
        brain_hash = sha256_hex(brain_prompt.encode("utf-8")) if brain_prompt else ""

        personality_hash = ""
        try:
            if char and hasattr(char, "personality"):
                personality_hash = sha256_hex(char.personality.encode("utf-8"))
        except Exception:
            pass

        # Session info
        session_file = ""
        session_file_hash = ""
        try:
            sf = server.observer._current_session_file
            if sf:
                session_file = sf.name
                if sf.exists():
                    session_file_hash = sha256_hex(sf.read_bytes())
        except Exception:
            pass

        session_model = ""
        try:
            session_model = server._llm_config.get("model", "")
        except Exception:
            pass

        hermes_home_path = str(getattr(server, "hermes_home", ""))

        header = {
            "seq": -1,
            "wall_ts_ms": 0,
            "type": "metadata",

            "recording_id": self._recording_id,
            "recording_version": RECORDING_VERSION,
            "recording_format_version": RECORDING_FORMAT_VERSION,
            "companion_version": "2.1.0",
            "companion_commit": "",

            "session": {
                "session_id": session_id,
                "session_file": session_file,
                "session_file_hash": f"sha256:{session_file_hash}" if session_file_hash else "",
                "session_model": session_model,
                "session_started_at_utc": "",
                "session_message_count_initial": 0,
                "hermes_home_path": hermes_home_path,
            },

            "companion_config": {
                "profile": profile,
                "character": character,
                "name": char.name if char else "",
                "character_personality_hash": f"sha256:{personality_hash}" if personality_hash else "",
                "character_hermes_profiles": char.hermes_profiles if char else [],
                "verbosity": settings.get("verbosity", "full"),
                "tts_enabled": settings.get("tts_enabled", True),
                "observer_enabled": settings.get("observer_enabled", True),
                "context_budget": settings.get("context_budget", 3),
                "react_cooldown": settings.get("react_cooldown", 15),
                "show_tool_details": settings.get("show_tool_details", True),
                "tts_engine": getattr(server, "_tts_config", {}).get("engine", ""),
                "godmode_enabled": getattr(server, "_godmode", False),
            },

            "recording_session": {
                "started_at_utc": self._recording_start_utc,
                "ended_at_utc": None,
                "recording_duration_ms": None,
                "total_events": None,
                "recording_reason": reason,
                "hostname": socket.gethostname(),
                "platform": "linux",  # WSL reports as linux
            },

            "schema_info": {
                "event_types_count": 35,
                "audio_stored_externally": True,
                "audio_cache_dir": str(self._audio_cache_dir),
                "context_capture_enabled": True,
                "frame_data_stored": False,
                "privacy_redactions_applied": False,
            },
        }

        self._enqueue(header)
        # Note: header has seq=-1. Real events start at seq=0 via _record()

    # ────────────────────────────────────────────────────────────────────────
    # Server hooking / unhooking
    # ────────────────────────────────────────────────────────────────────────

    def _hook_server(self) -> None:
        """Replace server methods with recording wrappers."""
        import asyncio

        server = self._server
        recorder = self  # capture for closures

        # ── Save originals ─────────────────────────────────────────────────
        self._orig_broadcast = server._broadcast
        self._orig_broadcast_audio = server._broadcast_audio_to_renderers
        self._orig_on_hermes_event = server._on_hermes_event

        # ── Wrap _broadcast ────────────────────────────────────────────────
        orig_broadcast = self._orig_broadcast

        async def wrapped_broadcast(message: str, roles=None):
            # Call original first
            await orig_broadcast(message, roles)
            # Then record
            if recorder._recording:
                recorder._on_broadcast(message)

        server._broadcast = wrapped_broadcast

        # ── Wrap _broadcast_audio_to_renderers ─────────────────────────────
        orig_broadcast_audio = self._orig_broadcast_audio

        async def wrapped_broadcast_audio(wav_bytes: bytes, duration_s=None, audio_path=None):
            if recorder._recording:
                recorder._on_audio_broadcast(wav_bytes, duration_s)
            await orig_broadcast_audio(wav_bytes, duration_s=duration_s, audio_path=audio_path)

        server._broadcast_audio_to_renderers = wrapped_broadcast_audio

        # ── Wrap _on_hermes_event ──────────────────────────────────────────
        orig_on_hermes_event = self._orig_on_hermes_event

        async def wrapped_on_hermes_event(event_type: str, context: dict):
            if recorder._recording:
                recorder._on_hermes_event_input(event_type, context)
            await orig_on_hermes_event(event_type, context)

        server._on_hermes_event = wrapped_on_hermes_event

        # ── Re-register with the observer ──────────────────────────────────
        # The observer registered self._on_hermes_event as its callback at
        # init time and holds a direct reference to the original.  Without
        # re-registration, observer events bypass the recording wrapper.
        observer = getattr(server, 'observer', None)
        if observer and hasattr(observer, 'on_event'):
            observer.on_event(wrapped_on_hermes_event)

        logger.debug("Recorder hooks installed")

    def _unhook_server(self) -> None:
        """Restore original server methods."""
        server = self._server
        if self._orig_broadcast:
            server._broadcast = self._orig_broadcast
        if self._orig_broadcast_audio:
            server._broadcast_audio_to_renderers = self._orig_broadcast_audio
        if self._orig_on_hermes_event:
            # Restore the observer's callback to the original method.
            # The observer holds its own reference to the callback; without
            # this re-registration it would keep calling the recorder wrapper
            # even after the recorder has stopped.
            observer = getattr(server, 'observer', None)
            if observer and hasattr(observer, 'on_event'):
                observer.on_event(self._orig_on_hermes_event)
            server._on_hermes_event = self._orig_on_hermes_event
        logger.debug("Recorder hooks removed")

    # ────────────────────────────────────────────────────────────────────────
    # Broadcast interceptor
    # ────────────────────────────────────────────────────────────────────────

    def _on_broadcast(self, message: str) -> None:
        """Parse a broadcast message and record the appropriate event."""
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return

        msg_type = data.get("type", "")

        # ── Scene player result broadcasts ─────────────────────────────────
        if msg_type in SCENE_RESULT_BROADCASTS:
            rec_type = SCENE_RESULT_BROADCASTS[msg_type]
            fields = {k: v for k, v in data.items() if k != "type"}
            self._record(rec_type, **fields)
            return

        # ── Status broadcast ───────────────────────────────────────────────
        if msg_type == "status":
            self._record_output_status(data.get("status", ""))
            return

        # ── Text broadcast (part of a quip) ────────────────────────────────
        if msg_type == "text":
            self._record_output_text(
                text=data.get("text", ""),
                expression=data.get("expression", "normal"),
                reaction_kind=self._pending_quip.get("reaction_kind", "") if self._pending_quip else "",
                trigger_quip_seq=self._last_quip_seq,
            )
            # Also record the quip now (text broadcast means quip is being delivered)
            if self._pending_quip:
                self._record("output_quip", **self._pending_quip)
                self._pending_quip = None
            return

        # ── Audio stop ─────────────────────────────────────────────────────
        if msg_type == "audio_stop":
            reason = self._infer_audio_stop_reason()
            self._record_output_audio_stop(reason=reason)
            return

        # ── Frame broadcast (throttled) ────────────────────────────────────
        if msg_type == "frame":
            self._maybe_record_frame(data)
            return

        # ── Model changed ──────────────────────────────────────────────────
        if msg_type == "model_changed":
            self._record_system_model_changed(
                model=data.get("model", ""),
                provider=getattr(self._server, "_llm_config", {}).get("provider", ""),
            )
            return

        # ── TTS engine changed ─────────────────────────────────────────────
        if msg_type == "tts_engine_changed":
            self._record_system_tts_engine_changed(engine=data.get("engine", ""))
            return

        # ── Godmode changed ────────────────────────────────────────────────
        if msg_type == "godmode_changed":
            self._record("system_godmode_changed", enabled=data.get("enabled", False))
            return

        # ── Character changed broadcasts ───────────────────────────────────
        if msg_type in CHARACTER_CHANGE_BROADCASTS:
            action_map = {
                "character_created": "created",
                "character_deleted": "deleted",
                "character_saved": "saved",
                "character_exported": "exported",
                "character_imported": "imported",
            }
            active_char = ""
            try:
                active_char = self._server.char_manager.active_id or ""
            except Exception:
                pass
            self._record("system_character_changed",
                action=action_map.get(msg_type, msg_type),
                character=data.get("id", data.get("character", "")),
                ok=data.get("ok", True),
                active_character=active_char,
            )
            return

        # ── Profile switch result ──────────────────────────────────────────
        if msg_type == "profile_switch_result":
            self._record("system_profile_switch_result",
                success=data.get("success", False),
                profile=data.get("profile", ""),
                new_character=data.get("active_character"),
                had_visible_characters=data.get("active_character") is not None,
                error=data.get("error"),
            )
            return

        # ── Scene player events ────────────────────────────────────────────
        if msg_type in BROADCAST_TO_RECORDING:
            rec_type = BROADCAST_TO_RECORDING[msg_type]
            fields = {k: v for k, v in data.items() if k != "type"}
            self._record(rec_type, **fields)
            return

        # ── Character switched broadcast ───────────────────────────────────
        if msg_type == "character_switched":
            fw = data.get("frame_width", 0)
            fh = data.get("frame_height", 0)
            if not fw:
                try:
                    fw, fh = self._server.compositor.frame_size
                except Exception:
                    pass
            self._record("output_character_switched",
                initiator=data.get("initiator", "system"),
                character=data.get("character", ""),
                name=data.get("name", ""),
                display_mode=data.get("display_mode", ""),
                frame_width=fw,
                frame_height=fh,
                request_id=data.get("request_id"),
                server_sent_at_ms=data.get("server_sent_at_ms", 0),
            )
            return

        # ── Character switch rejected ──────────────────────────────────────
        if msg_type == "character_switch_rejected":
            self._record("output_character_switch_rejected",
                character=data.get("character", ""),
                reason=data.get("reason", ""),
                bound_profile=data.get("bound_profile", []),
                active_profile=data.get("active_profile", ""),
                message=data.get("message", ""),
                request_id=data.get("request_id"),
            )
            return

        # ── Profile changed ────────────────────────────────────────────────
        if msg_type == "profile_changed":
            self._record("output_profile_changed",
                profile=data.get("profile", ""),
                active_character=data.get("active_character"),
            )
            return

        # ── Settings broadcast ─────────────────────────────────────────────
        if msg_type == "settings":
            # Settings broadcasts are frequent; only record on actual change
            # We track this by checking the settings key in the data
            # For now, we don't record from broadcast alone — set_setting hook handles it
            return

    def _maybe_record_frame(self, data: dict) -> None:
        """Record frame metadata, throttled to max 1 per 2 seconds."""
        now_ns = time.monotonic_ns()

        # Always record on expression change
        current_expr = data.get("expression", self._last_expression)
        expr_changed = current_expr != self._last_expression

        # Throttle: at most one per 2 seconds, unless expression changed
        if not expr_changed:
            if now_ns - self._last_frame_time_ns < self._frame_throttle_ns:
                return

        self._last_frame_time_ns = now_ns
        self._last_expression = current_expr
        self._frame_count += 1

        # Infer mouth_open from frame data if available, else from anim state
        mouth_open = 0.0
        try:
            anim = self._server.anim
            if anim:
                mouth_open = anim._get_mouth_index() / 10.0 if hasattr(anim, '_get_mouth_index') else 0.0
        except Exception:
            pass

        self._record("output_frame",
            expression=current_expr,
            mouth_open=round(mouth_open, 4),
            text=data.get("text", ""),
            server_sent_at_ms=data.get("server_sent_at_ms", 0),
            frame_size_bytes=len(json.dumps(data, ensure_ascii=False)),
        )

    def _infer_audio_stop_reason(self) -> str:
        """Infer the reason for an audio_stop broadcast."""
        server = self._server
        # Check if scene player is active
        try:
            sp = server.scene_player
            if sp._state in ("paused", "loaded"):
                return "scene"
        except Exception:
            pass
        # Check if approval is pending (priority cancel)
        if getattr(server, "_approval_pending", False):
            return "priority"
        # Check if character/profile switch is the cause
        return "manual"

    # ────────────────────────────────────────────────────────────────────────
    # Audio broadcast interceptor
    # ────────────────────────────────────────────────────────────────────────

    def _on_audio_broadcast(self, wav_bytes: bytes, duration_s: Optional[float]) -> None:
        """Record audio metadata and cache the WAV data externally."""
        audio_hash = sha256_hex(wav_bytes)
        cache_key = audio_hash  # full 64-char hex

        # Write to audio cache if not already present
        if audio_hash not in self._seen_hashes:
            self._seen_hashes.add(audio_hash)
            cache_path = self._audio_cache_dir / f"{audio_hash}.wav"
            try:
                if not cache_path.exists():
                    cache_path.write_bytes(wav_bytes)
            except OSError as e:
                logger.warning(f"Audio cache write failed: {e}")

        # Determine TTS engine
        tts_engine = ""
        tts_voice = ""
        try:
            tts_cfg = getattr(self._server, "_tts_config", {})
            tts_engine = tts_cfg.get("engine", "")
            tts_voice = tts_cfg.get("voice", "default")
        except Exception:
            pass

        self._record("output_audio",
            audio_hash=f"sha256:{audio_hash}",
            audio_cache_key=cache_key,
            duration_s=round(duration_s, 3) if duration_s else 0.0,
            size_bytes=len(wav_bytes),
            format="wav",
            tts_engine=tts_engine,
            tts_voice=tts_voice,
            trigger_quip_seq=self._last_quip_seq,
        )

    # ────────────────────────────────────────────────────────────────────────
    # Hermes event interceptor
    # ────────────────────────────────────────────────────────────────────────

    def _on_hermes_event_input(self, event_type: str, context: dict) -> None:
        """Record an input_hermes_event from the observer."""
        # ── State snapshot before processing ───────────────────────────────
        self._record_state_snapshot("before_input_event", trigger_event_seq=None)

        # ── Track session_id ───────────────────────────────────────────────
        session_id = context.get("session_id", "")
        if session_id:
            self._last_session_id = session_id
        elif self._last_session_id:
            session_id = self._last_session_id

        # ── Record the input event ─────────────────────────────────────────
        seq = self._record("input_hermes_event",
            event_type=event_type,
            session_id=session_id,
            session=context.get("session", ""),
            profile_name=context.get("profile_name", ""),
            message_count=context.get("message_count", 0),
            context=self._sanitize_context_for_recording(event_type, context),
        )

        self._last_trigger_event_seq = seq

    def _sanitize_context_for_recording(self, event_type: str, context: dict) -> dict:
        """Extract and sanitize context fields appropriate for the event type."""
        # Start with a copy, removing internal tracking fields
        result = {k: v for k, v in context.items()
                  if k not in ("session_id", "session", "profile_name", "message_count")}

        # Add source if missing
        if "source" not in result:
            result["source"] = "session"

        return result

    # ────────────────────────────────────────────────────────────────────────
    # Recording control
    # ────────────────────────────────────────────────────────────────────────

    def _record_recording_control(self, action: str, reason: str) -> None:
        """Record a system_recording_control event."""
        session_id = ""
        try:
            session_id = self._server.observer._watched_session_id or ""
        except Exception:
            pass
        character = ""
        try:
            character = self._server.char_manager.active_id or ""
        except Exception:
            pass
        profile = getattr(self._server, "_active_profile", "default") or "default"

        self._record("system_recording_control",
            action=action,
            reason=reason,
            session_id=session_id,
            character=character,
            profile=profile,
            companion_version="2.1.0",
            hermes_home=str(getattr(self._server, "hermes_home", "")),
            timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        )

    # ────────────────────────────────────────────────────────────────────────
    # Specific event recorders (called from wrappers and hooks)
    # ────────────────────────────────────────────────────────────────────────

    def record_quip(
        self,
        quip_text: str,
        expression: str,
        reaction_kind: str,
        semantic: str,
        was_llm_generated: bool = True,
        was_fallback: bool = False,
        fallback_reason: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_latency_ms: int = 0,
        quip_raw_llm: Optional[str] = None,
        prompt_context_summary: str = "",
        was_redundant: bool = False,
        redundancy_check_passed: bool = True,
        has_audio: bool = True,
        trigger_event_seq: Optional[int] = None,
        trigger_event_type: str = "",
        audio_duration_s: float = 0.0,
        audio_size_bytes: int = 0,
        audio_hash: Optional[str] = None,
        audio_cache_key: Optional[str] = None,
        tts_engine: Optional[str] = None,
        tts_voice: Optional[str] = None,
    ) -> int:
        """Record an output_quip event.

        Called by server reaction handlers at quip delivery time.
        Returns the seq number for linking subsequent output_text/output_audio events.
        """
        if not self._recording:
            return -1

        # Gather defaults from server state
        server = self._server
        if llm_model is None:
            try:
                llm_model = server._llm_config.get("model", "")
            except Exception:
                pass
        if llm_provider is None:
            try:
                llm_provider = server._llm_config.get("provider", "")
            except Exception:
                pass
        if tts_engine is None:
            try:
                tts_engine = server._tts_config.get("engine", "")
            except Exception:
                pass
        if tts_voice is None:
            try:
                tts_voice = server._tts_config.get("voice", "default")
            except Exception:
                pass

        seq = self._record("output_quip",
            quip_text=quip_text,
            expression=expression,
            reaction_kind=reaction_kind,
            semantic=semantic,
            was_llm_generated=was_llm_generated,
            was_fallback=was_fallback,
            fallback_reason=fallback_reason,
            llm_model=llm_model,
            llm_provider=llm_provider,
            llm_latency_ms=llm_latency_ms,
            quip_raw_llm=quip_raw_llm,
            prompt_context_summary=prompt_context_summary[:1000] if prompt_context_summary else "",
            was_redundant=was_redundant,
            redundancy_check_passed=redundancy_check_passed,
            has_audio=has_audio,
            trigger_event_seq=trigger_event_seq or self._last_trigger_event_seq,
            trigger_event_type=trigger_event_type,
            text_broadcast=True,
            audio_broadcast=has_audio,
            audio_duration_s=audio_duration_s,
            audio_size_bytes=audio_size_bytes,
            audio_hash=audio_hash,
            audio_cache_key=audio_cache_key,
            tts_engine=tts_engine,
            tts_voice=tts_voice,
            status_broadcasts=[],  # populated incrementally
        )

        self._last_quip_seq = seq
        return seq

    def _record_output_status(self, status: str) -> None:
        """Record an output_status event."""
        self._record("output_status",
            status=status,
            trigger_event_seq=self._last_trigger_event_seq,
        )

    def _record_output_text(
        self, text: str, expression: str, reaction_kind: str, trigger_quip_seq: Optional[int]
    ) -> None:
        """Record an output_text event."""
        self._record("output_text",
            text=text,
            expression=expression,
            reaction_kind=reaction_kind,
            trigger_quip_seq=trigger_quip_seq or self._last_quip_seq,
        )

    def _record_output_audio_stop(self, reason: str) -> None:
        """Record an output_audio_stop event."""
        self._record("output_audio_stop",
            reason=reason,
            stopped_seq=self._last_quip_seq,
            trigger_event_seq=self._last_trigger_event_seq,
        )

    def record_expression(
        self, expression: str, reason: str,
        trigger_event_seq: Optional[int] = None,
        trigger_event_type: Optional[str] = None,
    ) -> None:
        """Record an output_expression event."""
        if not self._recording:
            return
        if expression == self._last_expression:
            return  # dedup
        self._last_expression = expression
        self._record("output_expression",
            expression=expression,
            trigger_event_seq=trigger_event_seq,
            trigger_event_type=trigger_event_type,
            reason=reason,
        )

    def _record_system_model_changed(self, model: str, provider: str) -> None:
        """Record a system_model_changed event."""
        self._record("system_model_changed", model=model, provider=provider)

    def _record_system_tts_engine_changed(self, engine: str) -> None:
        """Record a system_tts_engine_changed event."""
        self._record("system_tts_engine_changed", engine=engine)

    def record_settings_changed(self, key: str, old_value: Any, new_value: Any) -> None:
        """Record a system_settings_changed event."""
        if not self._recording:
            return
        full_settings = dict(getattr(self._server, "settings", {}))
        self._record("system_settings_changed",
            changed_key=key,
            old_value=old_value,
            new_value=new_value,
            full_settings=full_settings,
        )

    def record_character_switched(
        self, initiator: str, character: str, name: str,
        display_mode: str, previous_character: str = "",
        request_id: Optional[str] = None,
        frame_width: int = 0, frame_height: int = 0,
    ) -> None:
        """Record an input_character_switched event."""
        if not self._recording:
            return
        if not frame_width:
            try:
                fw, fh = self._server.compositor.frame_size
                frame_width, frame_height = fw, fh
            except Exception:
                pass
        self._record("input_character_switched",
            initiator=initiator,
            character=character,
            name=name,
            display_mode=display_mode,
            previous_character=previous_character,
            request_id=request_id,
            frame_width=frame_width,
            frame_height=frame_height,
        )

    def record_character_switch_rejected(
        self, character: str, reason: str, bound_profile: list,
        active_profile: str, message: str, request_id: Optional[str] = None,
    ) -> None:
        """Record an input_character_switch_rejected event."""
        if not self._recording:
            return
        self._record("input_character_switch_rejected",
            character=character,
            reason=reason,
            bound_profile=bound_profile,
            active_profile=active_profile,
            message=message,
            request_id=request_id,
        )

    def record_profile_changed(
        self, previous_profile: str, new_profile: str, initiator: str,
        trigger_event_seq: Optional[int] = None,
        auto_switched_character: bool = False,
        previous_character: str = "", new_character: str = "",
        had_visible_characters: bool = True,
    ) -> None:
        """Record an input_profile_changed event."""
        if not self._recording:
            return
        self._record("input_profile_changed",
            previous_profile=previous_profile,
            new_profile=new_profile,
            initiator=initiator,
            trigger_event_seq=trigger_event_seq or self._last_trigger_event_seq,
            auto_switched_character=auto_switched_character,
            previous_character=previous_character,
            new_character=new_character,
            had_visible_characters=had_visible_characters,
        )

    def record_reaction_suppressed(
        self, suppression_reason: str, reaction_kind: str,
        semantic: Optional[str] = None,
        significance: Optional[int] = None,
        trigger_event_seq: Optional[int] = None,
        trigger_event_type: str = "",
        gate_details: Optional[dict] = None,
    ) -> None:
        """Record an output_reaction_suppressed event."""
        if not self._recording:
            return
        self._record("output_reaction_suppressed",
            suppression_reason=suppression_reason,
            reaction_kind=reaction_kind,
            semantic=semantic,
            significance=significance,
            trigger_event_seq=trigger_event_seq or self._last_trigger_event_seq,
            trigger_event_type=trigger_event_type,
            gate_details=gate_details or {},
        )

    def record_system_error(self, error_type: str, message: str, context: Optional[dict] = None) -> None:
        """Record a system_error event."""
        if not self._recording:
            return
        self._record("system_error",
            error_type=error_type,
            message=message,
            context=context or {},
        )

    def record_context_snapshot(
        self,
        trigger_quip_seq: int,
        reaction_kind: str,
        brain_system_prompt: str = "",
        user_prompt: str = "",
        quip_history_at_time: Optional[list] = None,
        recent_comment_context: str = "",
        llm_messages_sent: Optional[list] = None,
        model_used: str = "",
        provider_used: str = "",
        godmode_enabled: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 150,
        raw_llm_response: str = "",
    ) -> None:
        """Record a context_snapshot event for a generated quip."""
        if not self._recording:
            return

        brain_prompt_length = len(brain_system_prompt)
        brain_prompt_hash = sha256_hex(brain_system_prompt.encode("utf-8")) if brain_system_prompt else ""
        user_prompt_length = len(user_prompt)
        user_prompt_token_estimate = max(1, user_prompt_length // 4)
        quip_history = quip_history_at_time or []
        llm_messages = llm_messages_sent or []

        self._record("context_snapshot",
            trigger_quip_seq=trigger_quip_seq,
            reaction_kind=reaction_kind,
            brain_system_prompt=brain_system_prompt,
            brain_prompt_length_chars=brain_prompt_length,
            brain_prompt_hash=f"sha256:{brain_prompt_hash}" if brain_prompt_hash else "",
            user_prompt=user_prompt[:2000] if user_prompt else "",
            user_prompt_length_chars=user_prompt_length,
            user_prompt_token_estimate=user_prompt_token_estimate,
            quip_history_at_time=quip_history,
            quip_history_count=len(quip_history),
            recent_comment_context=recent_comment_context,
            recent_comment_context_length=len(recent_comment_context),
            llm_messages_sent=llm_messages,
            llm_messages_count=len(llm_messages),
            llm_total_tokens_estimate=max(1, sum(len(json.dumps(m, ensure_ascii=False)) // 4 for m in llm_messages)),
            model_used=model_used,
            provider_used=provider_used,
            godmode_enabled=godmode_enabled,
            temperature=temperature,
            max_tokens=max_tokens,
            raw_llm_response=raw_llm_response,
        )

    # ────────────────────────────────────────────────────────────────────────
    # State snapshot
    # ────────────────────────────────────────────────────────────────────────

    def _record_state_snapshot(self, reason: str, trigger_event_seq: Optional[int] = None) -> None:
        """Capture a comprehensive state snapshot of the companion server."""
        if not self._recording:
            return

        server = self._server
        now = time.time()
        char_manager = server.char_manager
        active_char = char_manager.active

        # Character state
        character = {
            "active_id": char_manager.active_id or "",
            "active_name": active_char.name if active_char else "",
            "display_mode": active_char.display_mode if active_char else "",
            "hermes_profiles": active_char.hermes_profiles if active_char else [],
            "personality_md_hash": "",
            "allowed_expressions": list(server.compositor.expression_names) if server.compositor else [],
            "speech_allowed_expressions": [],
        }
        if active_char and hasattr(active_char, "personality"):
            character["personality_md_hash"] = f"sha256:{sha256_hex(active_char.personality.encode('utf-8'))}"
        if active_char and hasattr(active_char, "speech_allowed"):
            allowed = active_char.speech_allowed
            character["speech_allowed_expressions"] = [
                e.replace("_", "", 1) for e, ok in allowed.items() if ok and e != "normal"
            ]

        # Profile state
        profile = {
            "active_profile": getattr(server, "_active_profile", "default") or "default",
            "manual_switch_cooldown_active": (now - getattr(server, "_manual_profile_switch_time", 0)) < 10.0,
        }

        # Speech state
        speech_state = {
            "is_speaking": getattr(server, "_is_speaking", False),
            "is_reacting": getattr(server, "_is_reacting", False),
            "approval_pending": getattr(server, "_approval_pending", False),
            "suppress_frames": getattr(server, "_suppress_frames", False),
            "current_tts_task_active": (
                getattr(server, "_current_tts_task", None) is not None
                and not getattr(server, "_current_tts_task", None).done()
            ),
            "reaction_seq_counter": getattr(server, "_reaction_seq_counter", 0),
            "last_played_seq": getattr(server, "_last_played_seq", 0),
        }

        # Cooldowns
        cooldowns = {
            "last_react_time": round(getattr(server, "_last_react_time", 0), 3),
            "last_any_react_time": round(getattr(server, "_last_any_react_time", 0), 3),
            "last_tool_react_time": round(getattr(server, "_last_tool_react_time", 0), 3),
            "react_cooldown_s": getattr(server, "_react_cooldown", 15.0),
            "tool_cooldown_s": getattr(server, "_tool_cooldown", 8.0),
            "min_react_gap_s": getattr(server, "_min_react_gap", 4.0),
            "semantic_cooldown_s": getattr(server, "_semantic_cooldown", 15.0),
            "last_reaction_semantic": getattr(server, "_last_reaction_semantic", ""),
            "last_semantic_time": round(getattr(server, "_last_semantic_time", 0), 3),
            "prompt_reacted_this_turn": getattr(server, "_prompt_reacted_this_turn", False),
        }

        # Buffers
        tool_cluster = getattr(server, "_tool_cluster_buffer", [])
        speech_acc = getattr(server, "_speech_accumulator", [])
        buffers = {
            "tool_cluster_buffer_size": len(tool_cluster),
            "tool_cluster_buffer_tools": list({
                t for ev in tool_cluster for t in ev.get("tools", [])
            }),
            "speech_accumulator_size": len(speech_acc),
            "speech_accumulator_tools": list({
                t for ev in speech_acc for t in ev.get("tools", [])
            }),
            "pending_prompt_task_active": (
                getattr(server, "_pending_prompt_task", None) is not None
                and not getattr(server, "_pending_prompt_task", None).done()
            ),
            "pending_prompt_query": getattr(server, "_pending_prompt_query", ""),
        }

        # Context memory
        brain_prompt = getattr(server, "_brain_prompt", "")
        context_memory = {
            "quip_history_count": len(getattr(server, "_quip_history", [])),
            "recent_comment_history_count": len(getattr(server, "_recent_comment_history", [])),
            "recent_reaction_count": len(getattr(server, "_recent_reactions", [])),
            "brain_prompt_length_chars": len(brain_prompt),
            "brain_prompt_hash": f"sha256:{sha256_hex(brain_prompt.encode('utf-8'))}" if brain_prompt else "",
        }

        # Settings summary
        s = getattr(server, "settings", {})
        settings_summary = {
            "observer_enabled": s.get("observer_enabled", True),
            "verbosity": s.get("verbosity", "full"),
            "tts_enabled": s.get("tts_enabled", True),
            "context_budget": s.get("context_budget", 3),
            "react_cooldown": s.get("react_cooldown", 15),
            "idle_lines_enabled": s.get("idle_lines_enabled", True),
            "playback_volume": s.get("playback_volume", 0.8),
        }

        # Brain config
        tts_config = getattr(server, "_tts_config", {})
        llm_config = getattr(server, "_llm_config", {})
        brain_config = {
            "godmode_enabled": getattr(server, "_godmode", False),
            "session_watching": getattr(server, "_session_watching", True),
            "tts_engine": tts_config.get("engine", ""),
            "tts_voice": tts_config.get("voice", "default"),
            "llm_model": llm_config.get("model", ""),
            "llm_provider": llm_config.get("provider", ""),
        }

        # Gates
        gates = {
            "tool_cluster_window_s": getattr(server, "_tool_cluster_window", 2.0),
            "tool_min_significance": getattr(server, "_tool_min_significance", 3),
            "react_dedup_window": getattr(server, "_react_dedup_window", 5),
            "react_similarity_threshold": getattr(server, "_react_similarity_threshold", 0.85),
            "recent_comment_limit": getattr(server, "_recent_comment_limit", 6),
            "recent_comment_window_s": getattr(server, "_recent_comment_window_s", 180),
            "prompt_ack_delay_s": getattr(server, "_prompt_ack_delay", 0.0),
        }

        # Timers
        startup_elapsed = now - getattr(server, "_startup_time", now)
        timers = {
            "startup_grace_elapsed_s": round(startup_elapsed, 1),
            "idle_timer_s": round(getattr(server, "_idle_timer", 0), 3),
            "return_to_normal_delay_s": getattr(server, "_return_to_normal_delay", 6.0),
            "manual_expression_cooldown_active": getattr(server, "_manual_expression_cooldown", 0) > 0,
        }

        # Locks (check if locked without blocking)
        locks = {
            "tts_lock_locked": getattr(server, "_tts_lock", None) is not None and getattr(server._tts_lock, "_waiters", None) is not None,
            "llm_lock_locked": getattr(server, "_llm_lock", None) is not None and getattr(server._llm_lock, "_waiters", None) is not None,
            "switch_lock_locked": getattr(server, "_switch_lock", None) is not None and getattr(server._switch_lock, "_waiters", None) is not None,
        }

        self._record("state_snapshot",
            reason=reason,
            trigger_event_seq=trigger_event_seq,
            character=character,
            profile=profile,
            speech_state=speech_state,
            cooldowns=cooldowns,
            buffers=buffers,
            context_memory=context_memory,
            settings_summary=settings_summary,
            brain_config=brain_config,
            gates=gates,
            timers=timers,
            locks=locks,
        )

    # ────────────────────────────────────────────────────────────────────────
    # Audio started event (callable from server when renderer acks playback)
    # ────────────────────────────────────────────────────────────────────────

    def record_audio_started(self) -> None:
        """Record an output_audio_started event."""
        if not self._recording:
            return
        self._record("output_audio_started", trigger_quip_seq=self._last_quip_seq)

    # ────────────────────────────────────────────────────────────────────────
    # Summary footer (optional)
    # ────────────────────────────────────────────────────────────────────────

    def _write_summary_footer(self) -> None:
        """Write a summary footer line with final recording stats."""
        if not self._recording:
            return
        wall_ts_ms = int((time.monotonic_ns() - self._start_time_ns) / 1_000_000)
        self._enqueue({
            "seq": self._seq,
            "wall_ts_ms": wall_ts_ms,
            "type": "summary",
            "total_events": self._seq,
            "duration_ms": wall_ts_ms,
            "ended_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        })
