from __future__ import annotations

import asyncio
import logging
import socket
from pathlib import Path

from app.core.config import settings
from app.services.avatar.render_job_repository import DEMO_TENANT_ID, render_job_repository
from app.services.avatar.render_retry_policy import render_retry_policy
from app.services.avatar.runtime.base import RenderRequest
from app.services.media.media_path_builder import media_path_builder
from app.services.media.media_storage import media_storage
from app.services.queue.redis_streams import redis_streams
from app.services.tts.audio_normalizer import audio_normalizer
from app.services.tts.configured_tts import configured_tts
from app.services.tts.schemas import TTSRequest

logger = logging.getLogger(__name__)


def _build_runtime():
    provider = settings.AVATAR_RENDER_PROVIDER
    if provider == "modal":
        if not settings.MODAL_ENABLED:
            raise RuntimeError("Modal avatar runtime is disabled. Set MODAL_ENABLED=true to enable it explicitly.")
        from app.services.avatar.runtime.modal_runtime import ModalAvatarRuntime  # noqa: PLC0415
        return ModalAvatarRuntime()
    if provider == "local":
        from app.services.avatar.runtime.local_runtime import LocalMuseTalkRuntime  # noqa: PLC0415
        return LocalMuseTalkRuntime()
    if provider != "fake":
        raise RuntimeError(f"Unsupported avatar render provider: {provider}")
    from app.services.avatar.runtime.fake_runtime import FakeAvatarRuntime  # noqa: PLC0415
    return FakeAvatarRuntime()


class AvatarRenderWorker:
    def __init__(self) -> None:
        self.consumer_name = f"avatar-render-worker-{socket.gethostname()}"
        self.runtime = _build_runtime()

    async def run_forever(self) -> None:
        await redis_streams.ensure_group(
            settings.AVATAR_RENDER_STREAM,
            settings.AVATAR_RENDER_CONSUMER_GROUP,
        )
        logger.info(
            "AvatarRenderWorker started",
            extra={"consumer": self.consumer_name, "stream": settings.AVATAR_RENDER_STREAM},
        )
        while True:
            messages = await redis_streams.read_group(
                stream=settings.AVATAR_RENDER_STREAM,
                group=settings.AVATAR_RENDER_CONSUMER_GROUP,
                consumer=self.consumer_name,
            )
            for _, stream_messages in messages:
                for message_id, payload in stream_messages:
                    await self.process_message(message_id, payload)

    async def process_message(self, message_id: str, payload: dict[str, str]) -> None:
        job_id = payload.get("job_id", "")
        tenant_id = payload.get("tenant_id") or DEMO_TENANT_ID
        if not job_id:
            logger.warning("Received message without job_id", extra={"message_id": message_id})
            await redis_streams.ack(
                settings.AVATAR_RENDER_STREAM,
                settings.AVATAR_RENDER_CONSUMER_GROUP,
                message_id,
            )
            return

        try:
            await self._run_job(job_id, tenant_id)
        except Exception as exc:
            logger.exception("Avatar render job failed", extra={"job_id": job_id})
            await self._handle_failure(job_id, tenant_id, exc)

        await redis_streams.ack(
            settings.AVATAR_RENDER_STREAM,
            settings.AVATAR_RENDER_CONSUMER_GROUP,
            message_id,
        )

    async def _run_job(self, job_id: str, tenant_id: str) -> None:
        job = await render_job_repository.get(job_id)
        if job["status"] != "queued":
            logger.info(
                "Skipping non-queued job",
                extra={"job_id": job_id, "status": job["status"]},
            )
            return

        avatar_id: str = job["avatar_id"]
        input_text: str = job["input_text"]
        voice_id: str | None = job.get("voice_id")
        language: str = job.get("language") or "vi"

        # 1. TTS
        await render_job_repository.mark_generating_audio(job_id)
        audio_raw = media_path_builder.audio_path(job_id)
        tts_result = await configured_tts.synthesize(
            TTSRequest(
                text=input_text,
                output_path=audio_raw,
                voice_id=voice_id,
                language=language,
            )
        )
        audio_duration = tts_result.duration_seconds or 0.0

        if audio_duration > settings.AVATAR_MAX_AUDIO_SECONDS:
            raise ValueError(
                f"audio too long: {audio_duration:.1f}s exceeds max {settings.AVATAR_MAX_AUDIO_SECONDS}s"
            )

        # 2. Normalize
        audio_norm = media_path_builder.audio_normalized_path(job_id)
        await audio_normalizer.normalize(Path(str(tts_result.audio_path)), audio_norm)

        await render_job_repository.mark_rendering(job_id, str(audio_raw), audio_duration)

        # 3. Resolve avatar source
        from app.services.avatar.avatar_registry import avatar_registry, backend_root  # noqa: PLC0415

        assets_resp = avatar_registry.get_assets(avatar_id)
        assets_by_name = {a.name: a for a in assets_resp.assets}

        idle = assets_by_name.get("idle_video")
        source = assets_by_name.get("source_image")

        if idle and idle.exists:
            source_abs = backend_root() / idle.path
            source_type = "idle_video"
        elif source and source.exists:
            source_abs = backend_root() / source.path
            source_type = "source_image"
        else:
            raise FileNotFoundError(f"No source asset available for avatar {avatar_id!r}")

        render_result = await self.runtime.render(
            RenderRequest(
                job_id=job_id,
                avatar_id=avatar_id,
                audio_path=str(audio_norm),
                source_path=str(source_abs),
                source_type=source_type,
                fps=25,
            )
        )

        # 4. Persist
        await render_job_repository.mark_downloading(job_id)
        stored = media_storage.persist(
            job_id,
            rendered_video_src=Path(render_result.output_path),
            audio_src=audio_norm,
            metadata=render_result.metadata,
            quality_report={
                "job_id": job_id,
                "render_duration_seconds": render_result.render_duration_seconds,
                "source_type": source_type,
            },
        )

        await render_job_repository.mark_completed(
            job_id,
            video_path=stored.video_path or "",
            metadata_path=stored.metadata_path,
            quality_report_path=stored.quality_report_path,
            render_duration_seconds=render_result.render_duration_seconds,
        )

        # 5. Playout event
        await redis_streams.publish(
            settings.PLAYOUT_QUEUE_STREAM,
            {
                "job_id": job_id,
                "tenant_id": tenant_id,
                "video_path": stored.video_path or "",
                "audio_path": stored.audio_path or "",
                "avatar_id": avatar_id,
            },
        )
        try:
            from app.services.playout.playout_segment_service import playout_segment_service  # noqa: PLC0415

            await playout_segment_service.mark_render_job_ready(
                render_job_id=job_id,
                source_video_path=stored.video_path or "",
            )
        except Exception:
            logger.exception("Failed to mark playout segment ready", extra={"job_id": job_id})

        logger.info("Avatar render completed", extra={"job_id": job_id})

    async def _handle_failure(self, job_id: str, tenant_id: str, exc: Exception) -> None:
        try:
            job = await render_job_repository.get(job_id)
        except Exception:
            logger.exception("Could not load job for failure handling", extra={"job_id": job_id})
            return

        error_code = render_retry_policy.classify_error(exc)
        error_message = render_retry_policy.safe_error_message(exc)

        if render_retry_policy.is_retryable(job):
            updated = await render_job_repository.increment_retry(job_id)
            await redis_streams.publish(
                settings.AVATAR_RENDER_STREAM,
                {"job_id": job_id, "tenant_id": tenant_id},
            )
            logger.info(
                "Avatar render job requeued",
                extra={"job_id": job_id, "retry_count": updated.get("retry_count")},
            )
        else:
            await render_job_repository.mark_failed(job_id, error_code, error_message)
            try:
                from app.services.playout.playout_segment_service import playout_segment_service  # noqa: PLC0415

                await playout_segment_service.mark_render_job_failed(
                    render_job_id=job_id,
                    error_code=error_code,
                    error_message=error_message,
                )
            except Exception:
                logger.exception("Failed to mark playout segment failed", extra={"job_id": job_id})
            logger.warning(
                "Avatar render job failed permanently",
                extra={"job_id": job_id, "error_code": error_code},
            )


async def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL.upper())
    await AvatarRenderWorker().run_forever()


if __name__ == "__main__":
    asyncio.run(main())
