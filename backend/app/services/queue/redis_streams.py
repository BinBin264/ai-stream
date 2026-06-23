import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisStreamClient:
    def __init__(self) -> None:
        self._client: Redis | None = None

    async def client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._client

    async def publish(self, stream: str, payload: dict[str, Any]) -> str:
        redis = await self.client()
        sanitized = {key: "" if value is None else str(value) for key, value in payload.items()}
        return await redis.xadd(stream, sanitized)

    async def ensure_group(self, stream: str, group: str) -> None:
        redis = await self.client()
        try:
            await redis.xgroup_create(stream, group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read_group(
        self,
        *,
        stream: str,
        group: str,
        consumer: str,
        count: int = 1,
        block_ms: int = 5000,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        await self.ensure_group(stream, group)
        redis = await self.client()
        return await redis.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        redis = await self.client()
        await redis.xack(stream, group, message_id)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


redis_streams = RedisStreamClient()
