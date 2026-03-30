"""Voice plugin — provides speech-to-text and text-to-speech services.

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext

logger = logging.getLogger(__name__)


class VoicePlugin:
    """Bootstraps STTService and TTSService."""

    plugin_id: str = "capos.core.voice"
    plugin_name: str = "Voice"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.stt_service: Any = None
        self.tts_service: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root
        voice_settings = ctx.plugin_settings(self.plugin_id)

        # --- STTService ---
        try:
            from system.core.voice import STTService

            self.stt_service = STTService(
                provider=voice_settings.get("stt_provider", "whisper_api"),
                api_key=voice_settings.get("stt_api_key", ""),
                language=voice_settings.get("language", "es"),
            )
            logger.info("Created STTService")
        except Exception:
            logger.exception("Failed to create STTService")

        # --- TTSService ---
        try:
            from system.core.voice import TTSService

            self.tts_service = TTSService(
                provider=voice_settings.get("tts_provider", "openai"),
                api_key=voice_settings.get("tts_api_key", ""),
                voice=voice_settings.get("voice", "nova"),
                speed=float(voice_settings.get("speed", 1.0)),
                output_dir=workspace_root / "artifacts" / "voice",
            )
            logger.info("Created TTSService")
        except Exception:
            logger.exception("Failed to create TTSService")

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import voice_handlers
        router.add("POST", "/voice/transcribe", voice_handlers.transcribe)
        router.add("POST", "/voice/synthesize", voice_handlers.synthesize)
        router.add("GET", "/voice/config", voice_handlers.voice_config)

    def start(self) -> None:
        """Voice services are passive — nothing to start."""

    def stop(self) -> None:
        """Voice services are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> VoicePlugin:
    """Entry-point factory used by the plugin loader."""
    return VoicePlugin()
