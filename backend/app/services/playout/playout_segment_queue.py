from __future__ import annotations

from app.core.config import settings
from app.services.queue.redis_streams import redis_streams


class PlayoutSegmentQueue:
    async def publish_ready(self, *, session_id: str, segment_id: str, priority: str) -> None:
        await redis_streams.publish(
            settings.PLAYOUT_SEGMENT_READY_STREAM,
            {
                "event_type": "playout.segment.ready",
                "session_id": session_id,
                "segment_id": segment_id,
                "priority": priority,
            },
        )

    async def publish_control(self, *, session_id: str, action: str, force: bool = False) -> None:
        await redis_streams.publish(
            settings.PLAYOUT_SESSION_CONTROL_STREAM,
            {
                "event_type": f"playout.session.{action}",
                "session_id": session_id,
                "action": action,
                "force": force,
            },
        )

    async def publish_event(self, payload: dict) -> None:
        await redis_streams.publish(settings.PLAYOUT_RUNTIME_EVENTS_STREAM, payload)


playout_segment_queue = PlayoutSegmentQueue()

