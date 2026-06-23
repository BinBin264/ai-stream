import logging
import socket

from app.core.config import settings
from app.models.domain import LiveComment
from app.services.comments.repository import live_comment_repository
from app.services.queue.redis_streams import redis_streams

logger = logging.getLogger(__name__)
DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


class CommentQueue:
    def __init__(self) -> None:
        self.consumer_name = f"comment-worker-{socket.gethostname()}"
        self._inflight: dict[str, str] = {}

    async def put(self, comment: LiveComment) -> None:
        await redis_streams.publish(
            settings.STREAM_COMMENTS,
            {
                "comment_id": comment.id,
                "tenant_id": comment.tenant_id,
                "live_session_id": comment.live_session_id or comment.live_id,
                "priority": comment.priority,
            },
        )

    async def get(self) -> LiveComment:
        while True:
            messages = await redis_streams.read_group(
                stream=settings.STREAM_COMMENTS,
                group=settings.REDIS_GROUP_COMMENTS,
                consumer=self.consumer_name,
            )
            for _, stream_messages in messages:
                for message_id, payload in stream_messages:
                    comment_id = payload.get("comment_id")
                    tenant_id = payload.get("tenant_id") or DEMO_TENANT_ID
                    comment = await live_comment_repository.get(str(comment_id), tenant_id=tenant_id)
                    if not comment:
                        logger.warning("Comment stream item has no local comment", extra={"comment_id": comment_id})
                        await redis_streams.ack(settings.STREAM_COMMENTS, settings.REDIS_GROUP_COMMENTS, message_id)
                        continue
                    self._inflight[comment.id] = message_id
                    return comment

    async def ack(self, message_id: str) -> None:
        await redis_streams.ack(settings.STREAM_COMMENTS, settings.REDIS_GROUP_COMMENTS, message_id)

    async def ack_comment(self, comment_id: str) -> None:
        message_id = self._inflight.pop(comment_id, None)
        if message_id:
            await self.ack(message_id)

    def size(self) -> int:
        return 0


comment_queue = CommentQueue()
