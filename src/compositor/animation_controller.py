"""
Nous Companion — Animation Controller

Drives the character animation:
  - Mouth: audio RMS → mouth sprite index
  - Eyes: random blink timer
  - Expression: switchable expression groups
  - Composited frames sent to renderer via WebSocket
"""

import asyncio
import base64
import io
import json
import logging
import random
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from compositor.cutout_compositor import CutoutCompositor
from compositor.audio_analyzer import AudioAnalyzer

logger = logging.getLogger(__name__)


class AnimationController:
    """Animation state machine for a Nous Companion character."""

    def __init__(self, compositor: CutoutCompositor, fps: int = 30):
        self.compositor = compositor
        self.fps = fps
        self.frame_interval = 1.0 / fps

        # Current state
        self.expression: str = "normal"
        self.mouth_open: float = 0.0  # 0.0 = closed, 1.0 = fully open
        self.eye_index: int = -1  # -1 = no overlay (base head shows default), 0+ = eye sprite overlay
        self.sprite_index: int = 0  # For standalones, which sprite to show

        # Blink state
        self._blink_timer: float = 0
        self._blink_interval: float = random.uniform(2.5, 6.0)  # seconds between blinks
        self._blink_phase: str = "idle"  # idle, closing, opening
        self._blink_frame: int = 0

        # Mouth thresholds (configurable per character)
        self.mouth_open_threshold = 0.35
        self.mouth_close_threshold = 0.18

        # Audio state
        self._audio: Optional[AudioAnalyzer] = None
        self._audio_playing: bool = False
        self._audio_start_time: float = 0
        self._audio_frame: int = 0
        self._audio_diag = None

        # Expression transition state
        self._transition_active: bool = False
        self._transition_from: str = "normal"
        self._transition_progress: float = 0.0
        self._transition_duration: float = 0.30  # seconds

        # Callback to send frames
        self._send_callback = None

        # Flap interval: min ms between mouth sprite changes during speech
        self._last_mouth_change_time: float = 0.0

    def set_expression(self, expression: str):
        """Switch to a different expression group with smooth crossfade."""
        if expression == self.expression:
            return
        if expression in self.compositor.expression_names:
            self._transition_from = self.expression
            self._transition_active = True
            self._transition_progress = 0.0
            self.expression = expression
            # Reset mouth state when changing expression
            self._last_mouth_index = -1
            self._last_mouth_change_time = 0.0
            self.mouth_open = 0.0
            logger.debug(f"Expression transition: {self._transition_from} → {expression}")
        else:
            logger.warning(f"Unknown expression '{expression}'")

    def reset_state(self, expression: str = "normal", sprite_index: int = 0):
        """Hard-reset animation state without crossfading from the previous character."""
        if expression not in self.compositor.expression_names:
            expression = "normal" if "normal" in self.compositor.expression_names else self.compositor.expression_names[0]
        self.expression = expression
        self.sprite_index = sprite_index
        self.mouth_open = 0.0
        self.eye_index = -1
        self._last_mouth_index = -1
        self._last_mouth_change_time = 0.0
        self._audio_playing = False
        self._audio_frame = 0
        self._audio_start_time = 0
        self._audio_diag = None
        self._transition_active = False
        self._transition_from = expression
        self._transition_progress = 1.0
        self._blink_timer = 0
        self._blink_phase = "idle"
        self._blink_frame = 0

    def load_audio(self, wav_path: str | Path):
        """Load audio for lip-sync. Resets playback state so old timers don't pollute new audio."""
        self._audio_playing = False
        self._audio_frame = 0
        self._audio_start_time = 0
        self._audio_diag = None
        try:
            self._audio = AudioAnalyzer(wav_path, fps=self.fps)
            if self._audio and self._audio.total_frames:
                values = [self._audio.get_mouth_open(i) for i in range(self._audio.total_frames)]
                above_open = sum(1 for v in values if v >= self.mouth_open_threshold)
                above_close = sum(1 for v in values if v >= self.mouth_close_threshold)
                self._audio_diag = {
                    "frames": len(values),
                    "mean": sum(values) / len(values),
                    "max": max(values),
                    "above_open": above_open,
                    "above_close": above_close,
                    "mouth_changes": 0,
                    "non_closed_frames": 0,
                    "last_idx": -999,
                }
                print(
                    "[MOUTH-DIAG] loaded "
                    f"frames={len(values)} mean={self._audio_diag['mean']:.3f} "
                    f"max={self._audio_diag['max']:.3f} "
                    f"above_open={above_open} above_close={above_close} "
                    f"thresholds=open:{self.mouth_open_threshold:.2f}/close:{self.mouth_close_threshold:.2f}",
                    flush=True,
                )
            logger.info(f"Audio loaded: {self._audio.duration_s:.1f}s")
        except Exception as e:
            logger.error(f"Failed to load audio for lip-sync: {e}")
            self._audio = None

    def start_audio(self):
        """Start playing the audio (reset frame counter)."""
        if self._audio:
            self._audio_playing = True
            self._audio_start_time = time.monotonic()
            self._audio_frame = 0
            if self._audio_diag is not None:
                self._audio_diag["mouth_changes"] = 0
                self._audio_diag["non_closed_frames"] = 0
                self._audio_diag["last_idx"] = -999
            logger.debug("Audio playback started")

    def stop_audio(self):
        """Stop audio playback."""
        self._audio_playing = False
        self.mouth_open = 0.0
        self._audio_diag = None

    def _update_mouth(self, dt: float):
        """Update mouth position from audio amplitude — smoothed.
        Uses real elapsed time to stay in sync with actual audio playback."""
        if self._audio_playing and self._audio:
            # Compute frame from real elapsed time (keeps sync even if loop is slow)
            elapsed = time.monotonic() - getattr(self, '_audio_start_time', 0)
            self._audio_frame = int(elapsed * self.fps)

            if self._audio_frame >= self._audio.total_frames:
                # Add tail: ramp mouth closed smoothly after audio ends
                tail_frames = max(6, int(self.fps * 0.25))  # ~250ms tail
                tail_start = self._audio.total_frames
                if self._audio_frame < tail_start + tail_frames:
                    progress = (self._audio_frame - tail_start) / tail_frames
                    self.mouth_open *= (1.0 - progress * progress)  # ease-in
                    logger.debug(
                        "Mouth tail frame=%s/%s progress=%.2f mouth_open=%.3f",
                        self._audio_frame,
                        self._audio.total_frames,
                        progress,
                        self.mouth_open,
                    )
                else:
                    if self._audio_diag is not None:
                        print(
                            "[MOUTH-DIAG] complete "
                            f"frames={self._audio_diag['frames']} "
                            f"non_closed_frames={self._audio_diag['non_closed_frames']} "
                            f"mouth_changes={self._audio_diag['mouth_changes']} "
                            f"mean={self._audio_diag['mean']:.3f} "
                            f"max={self._audio_diag['max']:.3f}",
                            flush=True,
                        )
                    self._audio_playing = False
                    self.mouth_open = 0.0
                    print("[MOUTH] Playback complete — _audio_playing=False", flush=True)
                return

            target = self._audio.get_mouth_open(self._audio_frame)
            prev_mouth = self.mouth_open

            # Smooth interpolation — lerp toward target
            smooth = 0.85
            self.mouth_open += (target - self.mouth_open) * smooth
            mouth_idx = self._get_mouth_index()
            if self._audio_diag is not None:
                if mouth_idx >= 0:
                    self._audio_diag["non_closed_frames"] += 1
                if mouth_idx != self._audio_diag["last_idx"]:
                    self._audio_diag["mouth_changes"] += 1
                    self._audio_diag["last_idx"] = mouth_idx

            # Only log every 5th frame to avoid spam
            if self._audio_frame % 5 == 0 or abs(self.mouth_open - prev_mouth) > 0.3:
                logger.debug(
                    "Mouth frame=%s/%s elapsed=%.2fs target=%.3f mo=%.3f->%.3f idx=%s",
                    self._audio_frame,
                    self._audio.total_frames,
                    elapsed,
                    target,
                    prev_mouth,
                    self.mouth_open,
                    mouth_idx,
                )

    def _update_eyes(self, dt: float):
        """Update eye blink state — slowed down."""
        eye_count = self.compositor.get_eye_count(self.expression)
        if eye_count <= 1:
            # No blink sprites available — use base head default (no overlay)
            self.eye_index = -1
            self._blink_phase = "idle"
            self._blink_timer = 0
            return

        BLINK_DELAY = 4  # only advance every N frames (~75ms per step at 30fps)

        if self._blink_phase == "idle":
            self._blink_timer += dt
            if self._blink_timer >= self._blink_interval:
                # Start blink — go from -1 (no overlay) to first eye sprite
                self._blink_phase = "closing"
                self._blink_frame = 0
                self._blink_timer = 0
                self._blink_interval = random.uniform(2.5, 6.0)
                self._blink_delay_counter = 0
                # Start from -1 (no overlay) and move to 0 (first eye sprite)
                self.eye_index = 0

        elif self._blink_phase == "closing":
            self._blink_delay_counter = getattr(self, '_blink_delay_counter', 0) + 1
            if self._blink_delay_counter >= BLINK_DELAY:
                self._blink_delay_counter = 0
                self._blink_frame += 1
                # Progress through eye states: 0 → 1 → ... (up to last sprite)
                self.eye_index = min(self._blink_frame, eye_count - 1)
                if self.eye_index >= eye_count - 1:
                    self._blink_phase = "opening"
                    self._blink_frame = eye_count - 1

        elif self._blink_phase == "opening":
            self._blink_delay_counter = getattr(self, '_blink_delay_counter', 0) + 1
            if self._blink_delay_counter >= BLINK_DELAY:
                self._blink_delay_counter = 0
                self._blink_frame -= 1
                # Go back through eye states: ... → 1 → 0
                self.eye_index = max(self._blink_frame, 0)
                if self.eye_index <= 0:
                    # Return to idle state — no overlay
                    self._blink_phase = "idle"
                    self.eye_index = -1

    def _get_mouth_index(self) -> int:
        """Map mouth_open (0–1) to a mouth sprite index. -1 = no overlay (mouth closed).
        Distributes mouth_open across ALL available sprites proportionally.
        Uses hysteresis to prevent rapid state flipping."""
        # Determine which expression to use for mouth count lookup.
        # During transition, use the NEW expression's sprites.
        expr = self.expression

        mouth_count = self.compositor.get_mouth_count(expr)
        if mouth_count == 0:
            return -1

        current_index = getattr(self, '_last_mouth_index', -1)

        # Hysteresis — different open/close points prevent flapping
        if current_index <= -1:
            # Mouth is closed — need higher value to open
            open_threshold = self.mouth_open_threshold
            if self.mouth_open < open_threshold:
                return -1
            # Opening transition
            logger.debug(
                "Mouth opening mo=%.3f threshold=%.3f count=%s",
                self.mouth_open,
                open_threshold,
                mouth_count,
            )
        else:
            # Mouth is open — need lower value to close
            close_threshold = self.mouth_close_threshold
            if self.mouth_open < close_threshold:
                self._last_mouth_index = -1
                logger.debug(
                    "Mouth closing mo=%.3f threshold=%.3f",
                    self.mouth_open,
                    close_threshold,
                )
                return -1

        # Mouth is open — distribute across ALL available sprites
        if mouth_count == 1:
            result = 0
        else:
            # Map mouth_open (0–1) proportionally to indices 0 .. mouth_count-1
            # Use a slight power curve so more time is spent in partially-open states
            t = max(0.0, min(1.0, self.mouth_open))
            t = t ** 0.7  # slight curve: low values still get some sprite index
            result = int(t * (mouth_count - 1))
            result = min(result, mouth_count - 1)

        # ── Flap interval cooldown: hold current sprite for at least
        # flap_interval_ms before switching to a new one.
        flap_ms = getattr(self, 'flap_interval_ms', 180)
        try:
            flap_ms = float(flap_ms)
        except (TypeError, ValueError):
            flap_ms = 0.0
        if flap_ms > 0 and result != current_index:
            elapsed_ms = (time.monotonic() - self._last_mouth_change_time) * 1000
            if elapsed_ms < flap_ms:
                return current_index  # cooldown not elapsed — hold position
        if result != current_index:
            self._last_mouth_change_time = time.monotonic()

        self._last_mouth_index = result
        return result

    def _update_transition(self, dt: float):
        """Advance expression crossfade progress."""
        if self._transition_active:
            self._transition_progress += dt / self._transition_duration
            if self._transition_progress >= 1.0:
                self._transition_active = False
                self._transition_progress = 1.0

    def get_frame(self) -> str:
        """Generate one composited frame as base64 PNG.
        Handles expression crossfading during transitions."""
        if self._transition_active:
            # Composite both expressions with the same eye/mouth state
            mouth_idx = self._get_mouth_index()
            from_img = self.compositor.composite(
                expression=self._transition_from,
                eye_index=self.eye_index,
                mouth_index=mouth_idx,
                sprite_index=self.sprite_index,
            )
            to_img = self.compositor.composite(
                expression=self.expression,
                eye_index=self.eye_index,
                mouth_index=mouth_idx,
                sprite_index=self.sprite_index,
            )
            # Ensure both images are the same size for blending
            if from_img.size != to_img.size:
                to_img = to_img.resize(from_img.size, Image.Resampling.LANCZOS)
            # Apply ease-in-out curve for smoother feel
            alpha = self._transition_progress
            alpha = alpha * alpha * (3.0 - 2.0 * alpha)  # smoothstep
            blended = Image.blend(from_img, to_img, alpha)
            buf = io.BytesIO()
            blended.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()

        return self.compositor.composite_to_base64(
            expression=self.expression,
            eye_index=self.eye_index,
            mouth_index=self._get_mouth_index(),
            sprite_index=self.sprite_index,
        )

    def build_event(self, event_type: str = "frame", text: str = "") -> str:
        """Build a JSON event with the current frame."""
        return json.dumps({
            "type": event_type,
            "frame": self.get_frame(),
            "text": text,
            "expression": self.expression,
            "mouth_open": round(self.mouth_open, 3),
            "server_sent_at_ms": int(time.time() * 1000),
        })

    async def run_loop(self, send_callback):
        """
        Main animation loop. Calls send_callback(json_str) for each frame.

        Args:
            send_callback: async function(json_event_string) to send to renderer
        """
        self._send_callback = send_callback
        logger.info(f"Animation loop started: {self.fps}fps")

        while True:
            dt = self.frame_interval

            # Update state
            self._update_mouth(dt)
            self._update_eyes(dt)
            self._update_transition(dt)

            # Send frame
            event = self.build_event()
            try:
                await send_callback(event)
            except Exception as e:
                logger.error(f"Send callback error: {e}")
                break

            await asyncio.sleep(dt)
