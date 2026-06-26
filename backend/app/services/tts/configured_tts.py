from __future__ import annotations

from app.core.config import settings
from app.services.tts.schemas import TTSRequest, TTSResult


class ConfiguredTTSProvider:
    """Selects the TTS provider from settings and delegates synthesis."""

    def __init__(self) -> None:
        self._provider_instance = None
        self._provider_key: str | None = None

    def _provider(self):
        # Cache provider instance — heavy models (viXTTS) load once per process
        if self._provider_key != settings.TTS_PROVIDER:
            self._provider_instance = self._build()
            self._provider_key = settings.TTS_PROVIDER
        return self._provider_instance

    def _build(self):
        if settings.TTS_PROVIDER == "fake":
            from app.services.tts.fake_tts import FakeTTSProvider  # noqa: PLC0415
            return FakeTTSProvider()
        if settings.TTS_PROVIDER in ("vietnamese", "edge"):
            from app.services.tts.vietnamese_tts import VietnameseTTSProvider  # noqa: PLC0415
            return VietnameseTTSProvider()
        if settings.TTS_PROVIDER == "vixtts":
            from app.services.tts.vixtts_tts import ViXTTSProvider  # noqa: PLC0415
            return ViXTTSProvider(settings.VIXTTS_MODEL_DIR, settings.VIXTTS_SPEAKER_WAV)
        if settings.TTS_PROVIDER == "modal":
            from app.services.tts.modal_tts import ModalTTSProvider  # noqa: PLC0415
            return ModalTTSProvider()
        raise RuntimeError(f"Unsupported TTS_PROVIDER: {settings.TTS_PROVIDER!r}")

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        return await self._provider().synthesize(request)


configured_tts = ConfiguredTTSProvider()
