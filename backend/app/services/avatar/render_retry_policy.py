from __future__ import annotations

from app.core.config import settings

_NON_RETRYABLE = frozenset({
    "audio_too_long",
    "text_too_long",
    "avatar_not_found",
    "tts_permanent",
    "render_validation_fail",
})


class RenderRetryPolicy:
    def is_retryable(self, job: dict) -> bool:
        if job.get("retry_count", 0) >= settings.AVATAR_RENDER_MAX_RETRIES:
            return False
        return job.get("error_code") not in _NON_RETRYABLE

    def classify_error(self, exc: Exception) -> str:
        msg = str(exc).lower()
        if "timeout" in msg:
            return "runtime_timeout"
        if "audio too long" in msg or "exceeds max" in msg:
            return "audio_too_long"
        if "avatar" in msg and "not found" in msg:
            return "avatar_not_found"
        if "download" in msg:
            return "download_fail"
        if isinstance(exc, (RuntimeError,)) and "tts" in type(exc).__name__.lower():
            return "tts_transient"
        return "unknown_error"

    def safe_error_message(self, exc: Exception) -> str:
        return str(exc)[:500]


render_retry_policy = RenderRetryPolicy()
