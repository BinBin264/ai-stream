from app.services.avatar.runtime.base import AvatarRuntime, RenderRequest, RenderResult, RuntimeHealth
from app.services.avatar.runtime.fake_runtime import FakeAvatarRuntime
from app.services.avatar.runtime.local_runtime import LocalMuseTalkRuntime

__all__ = [
    "AvatarRuntime",
    "FakeAvatarRuntime",
    "LocalMuseTalkRuntime",
    "RenderRequest",
    "RenderResult",
    "RuntimeHealth",
]
