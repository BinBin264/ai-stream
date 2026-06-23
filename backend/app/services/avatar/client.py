from app.core.config import settings
from app.services.avatar.base import AvatarRuntime
from app.services.avatar.fake import FakeAvatarRuntimeClient
from app.services.avatar.musetalk import MuseTalkRuntimeClient


def get_avatar_runtime() -> AvatarRuntime:
    if settings.AVATAR_RUNTIME_PROVIDER == "fake":
        return FakeAvatarRuntimeClient()
    if settings.AVATAR_RUNTIME_PROVIDER != "musetalk":
        raise RuntimeError(f"Unsupported avatar runtime provider: {settings.AVATAR_RUNTIME_PROVIDER}")
    return MuseTalkRuntimeClient()
