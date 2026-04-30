"""
Scene Player — plays scripted .nous-scene.json files as timed performances.

Pre-generates all TTS audio at load time so there is zero latency during playback.
Runs alongside the companion's live reaction system — live reactions arriving during
a scene are queued and play after the performance completes.

Usage:
    from scene_player import ScenePlayer
    player = ScenePlayer(companion_server_instance)
    await player.load_scene("path/to/demo.nous-scene.json")
    await player.play_scene()
"""

import asyncio
import base64
import json
import logging
import time
import wave
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ScenePlayer:
    """Plays scripted performance scenes with timed cues, expression changes, and TTS."""

    STATE_IDLE = "idle"
    STATE_LOADED = "loaded"
    STATE_PLAYING = "playing"
    STATE_PAUSED = "paused"
    STATE_DONE = "done"

    VALID_STATES = {STATE_IDLE, STATE_LOADED, STATE_PLAYING, STATE_PAUSED, STATE_DONE}

    def __init__(self, server):
        """Initialize scene player with a reference to a CompanionServer instance.

        Args:
            server: CompanionServer instance (uses anim.set_expression,
                    _synthesize_tts, _broadcast, _broadcast_audio_to_renderers, etc.)
        """
        self._server = server
        self._play_task: Optional[asyncio.Task] = None
        self.reset()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Reset all playback state back to idle."""
        self._state = self.STATE_IDLE
        self._scenes: list[dict] = []
        self._meta: dict = {}
        # Map: scene_index -> {base64, bytes, server_path, duration_s} | None
        self._pre_generated: dict[int, Optional[dict]] = {}
        self._current_scene_index: int = 0
        self._start_time: float = 0.0
        self._paused_elapsed: float = 0.0
        self._scene_file_path: str = ""
        # Track if we are mid-playback to suppress frame broadcasts during audio
        self._in_audio_block: bool = False

    @property
    def state(self) -> str:
        return self._state

    async def load_scene(self, path: str) -> dict:
        """Load a .nous-scene.json file, validate, and pre-generate all TTS audio.

        Args:
            path: Path to a .nous-scene.json file (absolute or relative to CWD).

        Returns:
            dict with keys: ok, meta, scene_count, tts_generated, tts_failed, state.
        """
        self.reset()
        self._scene_file_path = path

        file_path = Path(path)
        if not file_path.exists():
            msg = f"Scene file not found: {path}"
            logger.error(msg)
            return {"ok": False, "error": msg}

        # Parse JSON
        try:
            raw = file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON in scene file: {e}"
            logger.error(msg)
            return {"ok": False, "error": msg}
        except Exception as e:
            msg = f"Failed to read scene file: {e}"
            logger.error(msg)
            return {"ok": False, "error": msg}

        meta = data.get("meta", {})
        scenes = data.get("scenes", [])

        if not scenes:
            msg = "No scenes array in file (or empty)"
            logger.error(msg)
            return {"ok": False, "error": msg}

        # Validate each scene has required fields
        for i, sc in enumerate(scenes):
            if "time" not in sc:
                return {"ok": False, "error": f"Scene {i} missing required field 'time'"}
            if "expression" not in sc:
                return {"ok": False, "error": f"Scene {i} missing required field 'expression'"}
            if "line" not in sc:
                return {"ok": False, "error": f"Scene {i} missing required field 'line'"}

        # Sort by time ascending
        scenes = sorted(scenes, key=lambda s: float(s.get("time", 0)))

        self._meta = meta
        self._scenes = scenes

        # ── Pre-generate TTS for every scene ──────────────────────── #
        pre_gen_ok = 0
        pre_gen_fail = 0

        for i, scene in enumerate(scenes):
            line = scene.get("line", "").strip()
            if not line:
                self._pre_generated[i] = None
                continue

            expression = scene.get("expression", "normal")
            scene_speed = scene.get("speed")

            # Temporarily set TTS speed if specified in scene
            speed_restore = None
            if scene_speed is not None:
                try:
                    speed_val = float(scene_speed)
                    speed_restore = self._server._tts_config.get("speed", 1.0)
                    self._server._tts_config["speed"] = speed_val
                except (ValueError, TypeError):
                    pass

            try:
                b64_wav = await self._server._synthesize_tts(line, expression)

                if b64_wav:
                    wav_bytes = base64.b64decode(b64_wav)
                    server_path, _ = self._server._write_shared_temp_wav(wav_bytes)

                    # Read duration from WAV header
                    duration_s = self._duration_from_wav(server_path, line)

                    self._pre_generated[i] = {
                        "base64": b64_wav,
                        "bytes": wav_bytes,
                        "server_path": server_path,
                        "duration_s": duration_s,
                    }
                    pre_gen_ok += 1
                else:
                    self._pre_generated[i] = None
                    pre_gen_fail += 1
                    logger.warning(f"TTS returned None for scene {i}: \"{line[:50]}...\"")

            except Exception as e:
                logger.warning(f"TTS pre-generation failed for scene {i}: {e}")
                self._pre_generated[i] = None
                pre_gen_fail += 1

            finally:
                if speed_restore is not None:
                    self._server._tts_config["speed"] = speed_restore

        self._state = self.STATE_LOADED

        result = {
            "ok": True,
            "meta": meta,
            "scene_count": len(scenes),
            "tts_generated": pre_gen_ok,
            "tts_failed": pre_gen_fail,
            "state": self._state,
        }

        # Broadcast scene_loaded event to all connected clients
        await self._emit({"type": "scene_loaded", **result})

        self._server._debug_log(
            f"[SCENE] Loaded \"{meta.get('title', path)}\": "
            f"{len(scenes)} scenes, {pre_gen_ok} TTS OK, {pre_gen_fail} failed"
        )

        return result

    async def play_scene(self) -> dict:
        """Start or resume playback from the current position (scene 0 if loaded/done).

        Returns:
            dict with keys: ok, state, scene_count.
        """
        if self._state not in (self.STATE_LOADED, self.STATE_PAUSED, self.STATE_DONE):
            return {"ok": False, "error": f"Cannot play in state: {self._state}"}

        # Restart from beginning if done or loaded
        if self._state in (self.STATE_LOADED, self.STATE_DONE):
            self._current_scene_index = 0
            self._paused_elapsed = 0.0

        if self._state == self.STATE_PAUSED:
            # Resume: recalculate start_time so elapsed continues where it left off
            pass

        self._state = self.STATE_PLAYING
        self._start_time = time.time() - self._paused_elapsed

        # Cancel any stale play task
        self._cancel_play_task()

        self._play_task = asyncio.create_task(self._playback_loop())

        self._server._debug_log(
            f"[SCENE] Play started (resuming from scene {self._current_scene_index}, "
            f"elapsed={self._paused_elapsed:.2f}s)"
        )

        return {"ok": True, "state": self._state, "scene_count": len(self._scenes)}

    async def pause_scene(self) -> dict:
        """Pause playback immediately. Can be resumed with play_scene().

        Returns:
            dict with keys: ok, state, elapsed.
        """
        if self._state != self.STATE_PLAYING:
            return {"ok": False, "error": f"Cannot pause in state: {self._state}"}

        self._paused_elapsed = time.time() - self._start_time
        self._state = self.STATE_PAUSED

        self._cancel_play_task()

        # Stop any audio that is currently playing
        self._server.anim.stop_audio()
        await self._server._broadcast(
            json.dumps({"type": "audio_stop"}), roles={"renderer"}
        )
        self._server._invalidate_frame_signature()

        self._server._debug_log(
            f"[SCENE] Paused at scene {self._current_scene_index}, "
            f"elapsed={self._paused_elapsed:.2f}s"
        )

        return {"ok": True, "state": self._state, "elapsed": self._paused_elapsed}

    async def stop_scene(self) -> dict:
        """Stop playback and reset to the beginning.

        Returns:
            dict with keys: ok, state.
        """
        was_playing = self._state == self.STATE_PLAYING

        self._cancel_play_task()

        self._state = self.STATE_LOADED
        self._current_scene_index = 0
        self._paused_elapsed = 0.0

        # Stop any playing audio
        self._server.anim.stop_audio()
        await self._server._broadcast(
            json.dumps({"type": "audio_stop"}), roles={"renderer"}
        )
        self._server._invalidate_frame_signature()

        self._server._debug_log("[SCENE] Stopped and reset")

        return {"ok": True, "state": self._state}

    async def scene_status(self) -> dict:
        """Return current playback status without any side effects.

        Returns:
            dict with keys: state, current_scene_index, elapsed, scene_count, meta.
        """
        elapsed = self._calculate_elapsed()

        return {
            "state": self._state,
            "current_scene_index": self._current_scene_index,
            "elapsed": round(elapsed, 3),
            "scene_count": len(self._scenes),
            "meta": self._meta,
        }

    async def handle_command(self, data: dict, websocket) -> bool:
        """Dispatch an incoming WebSocket command to the scene player.

        Handles: load_scene, play_scene, pause_scene, stop_scene, scene_status.

        Args:
            data: Parsed JSON command dict (must have a "cmd" key).
            websocket: The WebSocket connection to respond on.

        Returns:
            True if the command was handled (recognized by scene player).
        """
        cmd = data.get("cmd", "")

        if cmd == "load_scene":
            path = data.get("path", "")
            if not path:
                await websocket.send(
                    json.dumps({"type": "error", "error": "Missing 'path' parameter"})
                )
                return True
            result = await self.load_scene(path)
            await websocket.send(
                json.dumps({"type": "load_scene_result", **result})
            )
            return True

        elif cmd == "play_scene":
            result = await self.play_scene()
            await websocket.send(
                json.dumps({"type": "play_scene_result", **result})
            )
            return True

        elif cmd == "pause_scene":
            result = await self.pause_scene()
            await websocket.send(
                json.dumps({"type": "pause_scene_result", **result})
            )
            return True

        elif cmd == "stop_scene":
            result = await self.stop_scene()
            await websocket.send(
                json.dumps({"type": "stop_scene_result", **result})
            )
            return True

        elif cmd == "scene_status":
            result = await self.scene_status()
            await websocket.send(
                json.dumps({"type": "scene_status", **result})
            )
            return True

        return False  # not a scene command

    # ------------------------------------------------------------------ #
    # Internal playback loop
    # ------------------------------------------------------------------ #

    async def _playback_loop(self) -> None:
        """Iterate through scenes in order, executing each cue at the right time."""
        try:
            for i in range(self._current_scene_index, len(self._scenes)):
                if self._state != self.STATE_PLAYING:
                    break

                scene = self._scenes[i]
                cue_time = float(scene.get("time", 0))
                expression = scene.get("expression", "normal")
                line = scene.get("line", "").strip()
                overlay_text = scene.get("overlay_text")
                action = scene.get("action")

                # ── Wait until cue time ────────────────────────────── #
                await self._wait_until(cue_time)
                if self._state != self.STATE_PLAYING:
                    break

                self._current_scene_index = i

                # ── Set expression and push frame ──────────────────── #
                self._server.anim.set_expression(expression)
                await self._server._send_current_frame_to_renderers()
                self._server._manual_expression_cooldown = 8.0
                self._server._idle_timer = 0

                elapsed = self._calculate_elapsed()

                # ── Emit scene_cue event ───────────────────────────── #
                cue_event = {
                    "type": "scene_cue",
                    "index": i,
                    "time": cue_time,
                    "elapsed": round(elapsed, 3),
                    "expression": expression,
                    "line": line,
                    "overlay_text": overlay_text,
                    "action": action,
                }
                await self._emit(cue_event)
                self._server._debug_log(
                    f"[SCENE] Cue {i} @ {cue_time:.1f}s: expr={expression} "
                    f"line=\"{line[:50]}{'...' if len(line) > 50 else ''}\""
                )

                # ── Play TTS audio ─────────────────────────────────── #
                audio_info = self._pre_generated.get(i)
                if audio_info is not None and line:
                    await self._play_audio_block(audio_info)
                elif line:
                    # Line specified but TTS failed — brief pause
                    await self._wait_duration(0.5)

                # ── Emit overlay event (for video recording sync) ──── #
                if overlay_text:
                    elapsed_now = self._calculate_elapsed()
                    overlay_event = {
                        "type": "scene_overlay",
                        "text": overlay_text,
                        "time": cue_time,
                        "elapsed": round(elapsed_now, 3),
                    }
                    await self._emit(overlay_event)
                    self._server._debug_log(
                        f"[SCENE] Overlay: \"{overlay_text}\""
                    )

            # ── All scenes complete ────────────────────────────────── #
            if self._state == self.STATE_PLAYING:
                self._state = self.STATE_DONE
                total_elapsed = self._calculate_elapsed()
                await self._emit({
                    "type": "scene_complete",
                    "elapsed": round(total_elapsed, 3),
                    "scene_count": len(self._scenes),
                })
                self._server._debug_log(
                    f"[SCENE] Complete — {len(self._scenes)} scenes in "
                    f"{total_elapsed:.1f}s"
                )

        except asyncio.CancelledError:
            # Expected on pause/stop — do not emit complete event
            pass
        except Exception as exc:
            logger.error(f"Scene playback loop error: {exc}", exc_info=True)
            self._state = self.STATE_LOADED
            await self._emit({"type": "scene_error", "error": str(exc)})

    async def _wait_until(self, target_time: float) -> None:
        """Wait in small increments until the target elapsed time is reached."""
        while self._state == self.STATE_PLAYING:
            elapsed = self._calculate_elapsed()
            remaining = target_time - elapsed
            if remaining <= 0:
                return
            # Sleep at most 100ms at a time so pause/stop is responsive
            await asyncio.sleep(min(0.1, remaining))

    async def _wait_duration(self, seconds: float) -> None:
        """Wait for a duration, but break early if state changes."""
        deadline = time.time() + seconds
        while time.time() < deadline and self._state == self.STATE_PLAYING:
            await asyncio.sleep(min(0.05, deadline - time.time()))

    async def _play_audio_block(self, audio_info: dict) -> None:
        """Play pre-generated audio: load, broadcast, wait for completion."""
        wav_bytes = audio_info["bytes"]
        server_path = audio_info["server_path"]
        duration_s = audio_info["duration_s"]

        # Load into animation controller for lip-sync
        self._server.anim.load_audio(server_path)

        # Cache for renderer fallback requests
        self._server._cache_last_audio(audio_info["base64"], duration_s)

        # Broadcast audio to all renderer clients
        self._in_audio_block = True
        self._server._suppress_frames = True
        await self._server._broadcast_audio_to_renderers(
            wav_bytes,
            duration_s=duration_s,
            audio_path=server_path,
        )
        self._server._suppress_frames = False
        self._in_audio_block = False

        # Wait for audio to finish playing (broken early if paused/stopped)
        await self._wait_duration(duration_s)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _calculate_elapsed(self) -> float:
        """Return seconds elapsed since playback started (accounting for pauses)."""
        if self._state == self.STATE_PLAYING:
            return time.time() - self._start_time
        return self._paused_elapsed

    def _cancel_play_task(self) -> None:
        """Safely cancel the running playback task if any."""
        if self._play_task is not None and not self._play_task.done():
            self._play_task.cancel()
        self._play_task = None

    async def _emit(self, payload: dict) -> None:
        """Broadcast an event to all connected WebSocket clients."""
        try:
            await self._server._broadcast(json.dumps(payload))
        except Exception as e:
            logger.warning(f"Scene player broadcast error: {e}")

    @staticmethod
    def _duration_from_wav(wav_path: str, fallback_text: str = "") -> float:
        """Extract audio duration from a WAV file header.

        Falls back to a rough estimate based on text length if the WAV
        header cannot be read.
        """
        try:
            with wave.open(wav_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / rate
        except (wave.Error, FileNotFoundError, OSError) as e:
            logger.warning(f"Could not read WAV duration from {wav_path}: {e}")

        # Rough fallback: ~80ms per character
        return max(0.5, len(fallback_text) * 0.08)
