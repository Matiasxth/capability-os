"""Speech-to-Text service — converts audio files to text.

Supports:
  - OpenAI Whisper API (cloud, accurate, multilingual)
  - Local Whisper via openai-whisper package (offline, GPU recommended)
  - Fallback: returns error if no provider configured
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


class STTService:
    """Transcribes audio files to text."""

    def __init__(
        self,
        provider: str = "whisper_api",
        api_key: str = "",
        language: str = "es",
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._language = language

    def configure(self, config: dict[str, Any]) -> None:
        self._provider = config.get("stt_provider", self._provider)
        self._api_key = config.get("stt_api_key") or config.get("api_key") or self._api_key
        self._language = config.get("language", self._language)

    def transcribe(self, audio_path: str | Path, language: str | None = None) -> dict[str, Any]:
        """Transcribe an audio file to text.

        Returns: {"text": "transcribed text", "language": "es", "duration_s": 4.2}
        """
        lang = language or self._language
        path = Path(audio_path)

        if not path.exists():
            return {"text": "", "error": f"File not found: {path}"}

        if self._provider == "whisper_api":
            return self._whisper_api(path, lang)
        elif self._provider == "whisper_local":
            return self._whisper_local(path, lang)
        else:
            return {"text": "", "error": f"Unknown STT provider: {self._provider}"}

    def transcribe_bytes(self, audio_bytes: bytes, format: str = "ogg", language: str | None = None) -> dict[str, Any]:
        """Transcribe audio bytes (e.g., from WhatsApp voice message)."""
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        try:
            return self.transcribe(tmp_path, language)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _whisper_api(self, path: Path, language: str) -> dict[str, Any]:
        """Transcribe via OpenAI Whisper API (works with OpenAI and Groq)."""
        if not self._api_key:
            return {"text": "", "error": "No API key configured for Whisper"}

        import io
        boundary = "----CapOSBoundary"
        body = io.BytesIO()

        # Build multipart form data
        body.write(f"--{boundary}\r\n".encode())
        body.write(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.write(b"whisper-1\r\n")

        body.write(f"--{boundary}\r\n".encode())
        body.write(b'Content-Disposition: form-data; name="language"\r\n\r\n')
        body.write(f"{language}\r\n".encode())

        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode())
        body.write(b"Content-Type: audio/ogg\r\n\r\n")
        body.write(path.read_bytes())
        body.write(f"\r\n--{boundary}--\r\n".encode())

        data = body.getvalue()

        # Determine base URL
        base_url = "https://api.openai.com/v1"
        req = Request(
            f"{base_url}/audio/transcriptions",
            data=data,
            method="POST",
        )
        req.add_header("Authorization", f"Bearer {self._api_key}")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                return {"text": result.get("text", ""), "language": language}
        except Exception as exc:
            return {"text": "", "error": f"Whisper API error: {exc}"}

    def _whisper_local(self, path: Path, language: str) -> dict[str, Any]:
        """Transcribe via local Whisper model."""
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(str(path), language=language)
            return {"text": result.get("text", ""), "language": language}
        except ImportError:
            return {"text": "", "error": "whisper package not installed. Run: pip install openai-whisper"}
        except Exception as exc:
            return {"text": "", "error": f"Local Whisper error: {exc}"}
