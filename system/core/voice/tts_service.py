"""Text-to-Speech service — converts text to audio files.

Supports:
  - OpenAI TTS API (cloud, high quality voices)
  - Web Speech API (browser-side, handled in frontend)
  - Fallback: returns error if no provider configured

Audio output is OGG/MP3 compatible with WhatsApp and Telegram.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


class TTSService:
    """Synthesizes text to audio files."""

    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        voice: str = "nova",
        speed: float = 1.0,
        output_dir: str | Path = "",
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._voice = voice
        self._speed = speed
        self._output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "capos_tts"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def configure(self, config: dict[str, Any]) -> None:
        self._provider = config.get("tts_provider", self._provider)
        self._api_key = config.get("tts_api_key") or config.get("api_key") or self._api_key
        self._voice = config.get("tts_voice", self._voice)
        self._speed = config.get("tts_speed", self._speed)

    def synthesize(self, text: str, output_format: str = "mp3") -> dict[str, Any]:
        """Convert text to audio file.

        Returns: {"audio_path": "/path/to/file.mp3", "format": "mp3", "size_bytes": N}
        """
        if not text.strip():
            return {"audio_path": "", "error": "Empty text"}

        # Truncate very long text
        text = text[:4000]

        if self._provider == "openai":
            return self._openai_tts(text, output_format)
        elif self._provider == "web_speech":
            # Web Speech is browser-side only — return text for frontend to handle
            return {"audio_path": "", "text": text, "provider": "web_speech", "use_frontend": True}
        else:
            return {"audio_path": "", "error": f"Unknown TTS provider: {self._provider}"}

    def synthesize_to_bytes(self, text: str, output_format: str = "mp3") -> bytes | None:
        """Synthesize and return raw audio bytes (for sending via messaging channels)."""
        result = self.synthesize(text, output_format)
        path = result.get("audio_path")
        if path and Path(path).exists():
            return Path(path).read_bytes()
        return None

    def _openai_tts(self, text: str, output_format: str) -> dict[str, Any]:
        """Synthesize via OpenAI TTS API."""
        if not self._api_key:
            return {"audio_path": "", "error": "No API key for TTS. Configure in Settings → Voice."}

        body = json.dumps({
            "model": "tts-1",
            "input": text,
            "voice": self._voice,
            "speed": self._speed,
            "response_format": output_format,
        }).encode()

        req = Request(
            "https://api.openai.com/v1/audio/speech",
            data=body,
            method="POST",
        )
        req.add_header("Authorization", f"Bearer {self._api_key}")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=30) as resp:
                audio_data = resp.read()
                # Save to file
                import uuid
                filename = f"tts_{uuid.uuid4().hex[:8]}.{output_format}"
                filepath = self._output_dir / filename
                filepath.write_bytes(audio_data)
                return {
                    "audio_path": str(filepath),
                    "format": output_format,
                    "size_bytes": len(audio_data),
                    "voice": self._voice,
                }
        except Exception as exc:
            return {"audio_path": "", "error": f"OpenAI TTS error: {exc}"}

    @property
    def available_voices(self) -> list[dict[str, str]]:
        """List available TTS voices."""
        if self._provider == "openai":
            return [
                {"id": "alloy", "name": "Alloy", "description": "Neutral, balanced"},
                {"id": "echo", "name": "Echo", "description": "Warm, deep"},
                {"id": "fable", "name": "Fable", "description": "British, expressive"},
                {"id": "nova", "name": "Nova", "description": "Friendly, conversational"},
                {"id": "onyx", "name": "Onyx", "description": "Deep, authoritative"},
                {"id": "shimmer", "name": "Shimmer", "description": "Soft, gentle"},
            ]
        return [{"id": "default", "name": "Default", "description": "System voice"}]
