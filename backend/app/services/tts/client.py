from app.core.config import settings
from app.services.tts.base import TTSProvider
from app.services.tts.fake import FakeTTSProvider


def get_tts_provider() -> TTSProvider:
    if settings.TTS_PROVIDER == "fake":
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
    raise RuntimeError(f"Unsupported TTS_PROVIDER: {settings.TTS_PROVIDER}")
