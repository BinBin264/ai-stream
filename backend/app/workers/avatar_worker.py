import asyncio
import logging
import socket

from app.core.config import settings
from app.services.media.publisher import DEMO_TENANT_ID
from app.services.media.render_orchestrator import media_render_orchestrator
from app.services.queue.redis_streams import redis_streams
from app.services.stream.playout_queue import playout_queue_service

logger = logging.getLogger(__name__)


class AvatarWorker:
    def __init__(self) -> None:
        self.consumer_name = f"avatar-worker-{socket.gethostname()}"

    async def run_forever(self) -> None:
        while True:
            messages = await redis_streams.read_group(
                stream=settings.STREAM_AVATAR,
                group=settings.REDIS_GROUP_AVATAR,
                consumer=self.consumer_name,
            )
            for _, stream_messages in messages:
                for message_id, payload in stream_messages:
                    await self.process_message(message_id, payload)

    async def process_message(self, message_id: str, payload: dict[str, str]) -> None:
        job_id = payload["render_job_id"]
        tenant_id = payload.get("tenant_id") or DEMO_TENANT_ID
        try:
            job = await media_render_orchestrator.submit_to_render_provider(tenant_id=tenant_id, job_id=job_id)
            await playout_queue_service.enqueue_render_job(job, tenant_id=tenant_id)
            await redis_streams.ack(settings.STREAM_AVATAR, settings.REDIS_GROUP_AVATAR, message_id)
        except Exception as exc:
            logger.exception("Failed to render avatar job", extra={"job_id": job_id, "tenant_id": tenant_id})
            try:
                await media_render_orchestrator.mark_failed(job_id, str(exc), tenant_id=tenant_id)
            except Exception:
                logger.exception("Failed to mark avatar job failed", extra={"job_id": job_id})


async def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL.upper())
    await AvatarWorker().run_forever()


if __name__ == "__main__":
    asyncio.run(main())
