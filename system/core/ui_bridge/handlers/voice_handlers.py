"""Voice API handlers: transcribe, synthesize, config."""
from __future__ import annotations

import base64
from http import HTTPStatus
from typing import Any


def _resp(code, data):
    return type("R", (), {"status_code": code.value, "payload": data})()


def transcribe(service: Any, payload: Any, **kw: Any):
    """Transcribe audio (base64 encoded) to text."""
    if not hasattr(service, "stt_service"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "STT service not available"})

    audio_b64 = (payload or {}).get("audio", "")
    format = (payload or {}).get("format", "ogg")
    language = (payload or {}).get("language")

    if not audio_b64:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Field 'audio' (base64) is required"})

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Invalid base64 audio data"})

    result = service.stt_service.transcribe_bytes(audio_bytes, format=format, language=language)
    return _resp(HTTPStatus.OK, result)


def synthesize(service: Any, payload: Any, **kw: Any):
    """Synthesize text to audio. Returns base64 audio or frontend instruction."""
    if not hasattr(service, "tts_service"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "TTS service not available"})

    text = (payload or {}).get("text", "")
    format = (payload or {}).get("format", "mp3")

    if not text.strip():
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Field 'text' is required"})

    result = service.tts_service.synthesize(text, output_format=format)

    # If audio file was generated, return as base64
    if result.get("audio_path"):
        from pathlib import Path
        path = Path(result["audio_path"])
        if path.exists():
            audio_b64 = base64.b64encode(path.read_bytes()).decode()
            result["audio_base64"] = audio_b64
            result["audio_url"] = f"data:audio/{format};base64,{audio_b64}"

    return _resp(HTTPStatus.OK, result)


def voice_config(service: Any, payload: Any, **kw: Any):
    """Get voice configuration and available voices."""
    voices = []
    if hasattr(service, "tts_service"):
        voices = service.tts_service.available_voices

    settings = service.settings_service.get_settings(mask_secrets=True)
    voice_settings = settings.get("voice", {})

    return _resp(HTTPStatus.OK, {
        "stt_provider": voice_settings.get("stt_provider", "whisper_api"),
        "tts_provider": voice_settings.get("tts_provider", "web_speech"),
        "tts_voice": voice_settings.get("tts_voice", "nova"),
        "tts_speed": voice_settings.get("tts_speed", 1.0),
        "auto_speak": voice_settings.get("auto_speak", False),
        "language": voice_settings.get("language", "es"),
        "available_voices": voices,
    })
