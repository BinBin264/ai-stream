import asyncio

from app.models.domain import LiveComment


class CommentQueue:
    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, str, LiveComment]] = asyncio.PriorityQueue()

    async def put(self, comment: LiveComment) -> None:
        # PriorityQueue returns the smallest value first, so invert priority.
        await self._queue.put((-comment.priority, comment.created_at.isoformat(), comment))

    async def get(self) -> LiveComment:
        _, _, comment = await self._queue.get()
        return comment

    def size(self) -> int:
        return self._queue.qsize()


comment_queue = CommentQueue()
