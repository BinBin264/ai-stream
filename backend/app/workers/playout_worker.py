import asyncio
import logging
import socket

from app.core.config import settings
from app.services.queue.redis_streams import redis_streams

logger = logging.getLogger(__name__)


class PlayoutWorker:
    def __init__(self) -> None:
        self.consumer_name = f"playout-worker-{socket.gethostname()}"

    async def run_forever(self) -> None:
        while True:
            messages = await redis_streams.read_group(
                stream=settings.STREAM_PLAYOUT,
                group=settings.REDIS_GROUP_PLAYOUT,
                consumer=self.consumer_name,
            )
            for _, stream_messages in messages:
                for message_id, payload in stream_messages:
                    logger.info("Received playout item", extra={"payload": payload})
                    await redis_streams.ack(settings.STREAM_PLAYOUT, settings.REDIS_GROUP_PLAYOUT, message_id)


async def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL.upper())
    await PlayoutWorker().run_forever()


if __name__ == "__main__":
    asyncio.run(main())
