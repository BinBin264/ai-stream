from app.core.config import settings
from app.services.tts.base import TTSProvider
from app.services.tts.elevenlabs import ElevenLabsTTSProvider
from app.services.tts.fake import FakeTTSProvider


def get_tts_provider() -> TTSProvider:
    if settings.TTS_PROVIDER == "fake":
        return FakeTTSProvider()
    if settings.TTS_PROVIDER == "elevenlabs":
        return ElevenLabsTTSProvider()
    raise RuntimeError(f"Unsupported TTS_PROVIDER: {settings.TTS_PROVIDER}")
