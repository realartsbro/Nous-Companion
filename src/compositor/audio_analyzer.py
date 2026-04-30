"""
Nous Companion — Audio Analyzer

Reads WAV audio and computes per-frame RMS amplitude,
mapping it to a mouth_open_amount (0.0–1.0) for lip-sync.
"""

import logging
import struct
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class AudioAnalyzer:
    """Analyzes WAV audio for mouth-sync amplitude data."""

    def __init__(self, wav_path: str | Path, fps: int = 30):
        self.wav_path = Path(wav_path)
        self.fps = fps

        if not self.wav_path.exists():
            raise FileNotFoundError(f"WAV file not found: {self.wav_path}")

        self._rms_frames: list[float] | None = None
        self._duration_s: float = 0
        self._sample_rate: int = 0

        self._analyze()

    def _analyze(self):
        """Read WAV and compute per-frame RMS values."""
        with wave.open(str(self.wav_path), "rb") as wav:
            self._sample_rate = wav.getframerate()
            n_channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            n_frames = wav.getnframes()

            self._duration_s = n_frames / self._sample_rate

            # Read all audio data
            raw = wav.readframes(n_frames)

        # Detect WAV audio format from file header (wave module strips header from readframes)
        wav_bytes = self.wav_path.read_bytes()
        audio_format = struct.unpack_from('<H', wav_bytes, 20)[0] if len(wav_bytes) >= 22 else 1

        # Convert to numpy array and normalize to -1.0..1.0
        if sample_width == 2 and audio_format == 1:  # 16-bit PCM
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 1:                       # 8-bit PCM
            samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
        elif sample_width == 4 and audio_format == 3: # 32-bit IEEE float
            samples32 = np.frombuffer(raw, dtype=np.float32)
            samples = np.clip(samples32, -1.0, 1.0).astype(np.float32)
        elif sample_width == 3:                       # 24-bit PCM
            samples24 = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
            samples_int = np.zeros(len(samples24), dtype=np.int32)
            for i in range(3):
                samples_int += samples24[:, i].astype(np.int32) << (i * 8)
            mask = samples_int >= 0x800000
            samples_int[mask] = samples_int[mask] - 0x1000000
            samples = samples_int.astype(np.float32) / 8388608.0
        else:
            raise ValueError(
                f"Unsupported WAV format: audio_format={audio_format}, "
                f"sample_width={sample_width}"
            )

        # Convert to mono if stereo
        if n_channels > 1:
            samples = samples.reshape(-1, n_channels).mean(axis=1)

        # Compute RMS per frame
        samples_per_frame = int(self._sample_rate / self.fps)
        n_output_frames = int(self._duration_s * self.fps)

        self._rms_frames = []
        for i in range(n_output_frames):
            start = i * samples_per_frame
            end = start + samples_per_frame
            chunk = samples[start:end]

            if len(chunk) == 0:
                self._rms_frames.append(0.0)
            else:
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                self._rms_frames.append(rms)

        # Normalize RMS to 0–1 range (use 95th percentile as max to handle peaks)
        if self._rms_frames:
            max_rms = np.percentile(self._rms_frames, 95)
            if max_rms > 0:
                self._rms_frames = [min(r / max_rms, 1.0) for r in self._rms_frames]

            # Temporal smoothing — lighter moving average
            smooth_window = 3
            smoothed = []
            for i in range(len(self._rms_frames)):
                start = max(0, i - smooth_window // 2)
                end = min(len(self._rms_frames), i + smooth_window // 2 + 1)
                smoothed.append(sum(self._rms_frames[start:end]) / (end - start))
            self._rms_frames = smoothed

            # Exaggerate peaks — power curve makes highs higher, lows lower
            self._rms_frames = [r ** 0.6 for r in self._rms_frames]

            # Strip trailing silence (prevents animation from running through
            # silent padding that some TTS engines append)
            silence_threshold = 0.02
            min_silence_frames = int(self.fps * 0.3)  # 300ms
            trailing_silent = 0
            for i in range(len(self._rms_frames) - 1, -1, -1):
                if self._rms_frames[i] < silence_threshold:
                    trailing_silent += 1
                else:
                    break
            if trailing_silent >= min_silence_frames:
                original_len = len(self._rms_frames)
                self._rms_frames = self._rms_frames[:-(trailing_silent - min_silence_frames // 2)]
                stripped = original_len - len(self._rms_frames)
                logger.info(f"Stripped {stripped} trailing silent frames ({stripped/self.fps:.2f}s)")

        logger.info(
            f"Audio analyzed: {self._duration_s:.1f}s, {len(self._rms_frames)} frames, "
            f"sample_rate={self._sample_rate}"
        )

    @property
    def duration_s(self) -> float:
        return self._duration_s

    @property
    def total_frames(self) -> int:
        return len(self._rms_frames) if self._rms_frames else 0

    def get_mouth_open(self, frame: int) -> float:
        """Get mouth_open_amount (0.0–1.0) for a given frame."""
        if not self._rms_frames or frame < 0 or frame >= len(self._rms_frames):
            return 0.0
        return self._rms_frames[frame]

    def get_mouth_open_at_time(self, time_s: float) -> float:
        """Get mouth_open_amount at a given time in seconds."""
        frame = int(time_s * self.fps)
        return self.get_mouth_open(frame)
