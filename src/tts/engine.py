"""
Nous Companion — TTS Interface

Pluggable TTS backends. Implement the TTSEngine protocol for any new engine.
Built-in: OmniVoice (voice cloning via a local or forwarded Gradio service),
OpenAI TTS, and a no-op stub.

OmniVoice runs on Windows (Pinokio). The server in WSL connects via Gradio API.
Do NOT install omnivoice or torch in WSL.
"""

import base64
import io
import logging
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from hermes_runtime import get_default_omnivoice_url

logger = logging.getLogger(__name__)


class TTSEngine(ABC):
    """Base class for TTS engines."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize speech from text.

        Returns:
            WAV audio bytes, or empty bytes if TTS is disabled.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine name (for logging/config)."""
        ...

    async def synthesize_base64(self, text: str) -> Optional[str]:
        """Synthesize and return base64-encoded audio. Returns None if no audio."""
        audio = await self.synthesize(text)
        if audio:
            return base64.b64encode(audio).decode()
        return None


class NoOpTTS(TTSEngine):
    """Stub engine — no audio output. Good for testing the visual pipeline."""

    @property
    def name(self) -> str:
        return "noop"

    async def synthesize(self, text: str) -> bytes:
        return b""


class OpenAITTS(TTSEngine):
    """OpenAI TTS API (tts-1, tts-1-hd)."""

    def __init__(
        self,
        api_key: str,
        model: str = "tts-1",
        voice: str = "nova",
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice

    @property
    def name(self) -> str:
        return f"openai:{self.voice}"

    async def synthesize(self, text: str) -> bytes:
        import aiohttp

        url = "https://api.openai.com/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "wav",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"OpenAI TTS error {resp.status}: {body[:200]}")
                    return b""
                return await resp.read()


class OmniVoiceTTS(TTSEngine):
    """
    OmniVoice TTS — voice cloning via Gradio API.

    Connects to OmniVoice running locally or via a forwarded host port.
    Default URL is auto-detected for localhost vs. WSL -> Windows host access.
    No local torch/CUDA dependencies in this process.
    """

    def __init__(
        self,
        reference_audio: Optional[str] = None,
        speed: float = 0.9,
        gradio_url: Optional[str] = None,
    ):
        self.reference_audio = reference_audio
        self.speed = speed
        self.gradio_url = gradio_url or get_default_omnivoice_url()
        self._client = None

    @property
    def name(self) -> str:
        return "omnivoice"

    def _get_client(self):
        """Lazy-load the Gradio client."""
        if self._client is None:
            try:
                from gradio_client import Client
                self._client = Client(self.gradio_url)
                logger.info(f"Connected to OmniVoice at {self.gradio_url}")
            except Exception as e:
                logger.warning(f"Failed to connect to OmniVoice at {self.gradio_url}: {e}")
                return None
        return self._client

    async def synthesize(self, text: str) -> bytes:
        client = self._get_client()
        if client is None:
            return b""

        if not self.reference_audio:
            logger.warning("No reference audio configured for voice cloning")
            return b""

        try:
            from gradio_client import handle_file

            result = client.predict(
                text=text,
                lang="English",
                ref_aud=handle_file(self.reference_audio),
                ref_text="",
                instruct="",
                ns=32, gs=2.0, dn=True, sp=self.speed, du=0.0, pp=True, po=True,
                api_name="/_clone_fn",
            )
            # result is (audio_file_path, status_string)
            audio_path = result[0] if isinstance(result, (tuple, list)) else result
            return Path(audio_path).read_bytes()
        except Exception as e:
            logger.error(f"OmniVoice error: {e}")
            return b""


import asyncio  # noqa: E402 — needed for OmniVoiceTTS


def create_engine(config: dict) -> TTSEngine:
    """
    Factory: create a TTS engine from config dict.

    Config format:
        engine: "omnivoice" | "openai" | "none"
        reference_audio: null | "/path/to/audio.wav"
        settings:
            api_key: "sk-..."        # for OpenAI
            model: "tts-1"           # for OpenAI
            voice: "nova"            # for OpenAI
    """
    engine_name = config.get("engine", "none")
    settings = config.get("settings", {})

    if engine_name == "none":
        return NoOpTTS()

    if engine_name == "openai":
        api_key = settings.get("api_key")
        if not api_key:
            logger.warning("OpenAI TTS configured but no api_key — using NoOp")
            return NoOpTTS()
        return OpenAITTS(
            api_key=api_key,
            model=settings.get("model", "tts-1"),
            voice=settings.get("voice", "nova"),
        )

    if engine_name == "omnivoice":
        return OmniVoiceTTS(
            reference_audio=config.get("reference_audio"),
            speed=settings.get("speed", 0.9),
            gradio_url=settings.get("gradio_url"),
        )

    logger.warning(f"Unknown TTS engine '{engine_name}' — using NoOp")
    return NoOpTTS()
