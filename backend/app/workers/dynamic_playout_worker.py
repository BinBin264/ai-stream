from __future__ import annotations

import asyncio
import logging
import socket

from app.core.config import settings
from app.services.playout.dynamic_runtime import DynamicPlayoutRuntime
from app.services.playout.playout_segment_queue import playout_segment_queue
from app.services.playout.playout_session_service import playout_session_service
from app.services.queue.redis_streams import redis_streams

logger = logging.getLogger(__name__)


class DynamicPlayoutWorker:
    def __init__(self) -> None:
        self.consumer_name = f"dynamic-playout-worker-{socket.gethostname()}"
        self._tasks: dict[str, asyncio.Task] = {}
        self._runtimes: dict[str, DynamicPlayoutRuntime] = {}

    async def run_forever(self) -> None:
        await redis_streams.ensure_group(settings.PLAYOUT_SESSION_CONTROL_STREAM, settings.PLAYOUT_RUNTIME_CONSUMER_GROUP)
        await redis_streams.ensure_group(settings.PLAYOUT_SEGMENT_READY_STREAM, settings.PLAYOUT_RUNTIME_CONSUMER_GROUP)
        logger.info("DynamicPlayoutWorker started", extra={"consumer": self.consumer_name})
        while True:
            await self._consume_control_once()
            await self._consume_ready_once()
            self._cleanup_finished()
            await asyncio.sleep(0.1)

    async def _consume_control_once(self) -> None:
        messages = await redis_streams.read_group(
            stream=settings.PLAYOUT_SESSION_CONTROL_STREAM,
            group=settings.PLAYOUT_RUNTIME_CONSUMER_GROUP,
            consumer=self.consumer_name,
            count=10,
            block_ms=250,
        )
        for _, stream_messages in messages:
            for message_id, payload in stream_messages:
                try:
                    await self._handle_control(payload)
                    await redis_streams.ack(settings.PLAYOUT_SESSION_CONTROL_STREAM, settings.PLAYOUT_RUNTIME_CONSUMER_GROUP, message_id)
                except Exception:
                    logger.exception("Failed to process playout control message", extra={"payload": payload})

    async def _consume_ready_once(self) -> None:
        messages = await redis_streams.read_group(
            stream=settings.PLAYOUT_SEGMENT_READY_STREAM,
            group=settings.PLAYOUT_RUNTIME_CONSUMER_GROUP,
            consumer=self.consumer_name,
            count=10,
            block_ms=100,
        )
        for _, stream_messages in messages:
            for message_id, payload in stream_messages:
                logger.info("Received ready playout segment", extra={"payload": payload})
                await redis_streams.ack(settings.PLAYOUT_SEGMENT_READY_STREAM, settings.PLAYOUT_RUNTIME_CONSUMER_GROUP, message_id)

    async def _handle_control(self, payload: dict[str, str]) -> None:
        session_id = payload.get("session_id", "")
        action = payload.get("action", "")
        if not session_id:
            return
        if action == "start":
            await self._start_session(session_id)
        elif action == "stop":
            await self._stop_session(session_id, force=str(payload.get("force", "")).lower() == "true")

    async def _start_session(self, session_id: str) -> None:
        existing = self._tasks.get(session_id)
        if existing and not existing.done():
            return
        runtime = DynamicPlayoutRuntime(session_id)
        task = asyncio.create_task(runtime.run())
        self._runtimes[session_id] = runtime
        self._tasks[session_id] = task
        await playout_segment_queue.publish_event(
            {"event_type": "playout.session.starting", "session_id": session_id}
        )

    async def _stop_session(self, session_id: str, *, force: bool) -> None:
        runtime = self._runtimes.get(session_id)
        if runtime and force:
            runtime.request_force_stop()
        await playout_session_service.request_stop(session_id, force=force)
        await playout_segment_queue.publish_event(
            {"event_type": "playout.session.stopping", "session_id": session_id, "force": force}
        )

    def _cleanup_finished(self) -> None:
        finished = [session_id for session_id, task in self._tasks.items() if task.done()]
        for session_id in finished:
            task = self._tasks.pop(session_id)
            self._runtimes.pop(session_id, None)
            if task.exception():
                logger.error("Dynamic playout task failed", extra={"session_id": session_id, "error": str(task.exception())})


async def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL.upper())
    await DynamicPlayoutWorker().run_forever()


if __name__ == "__main__":
    asyncio.run(main())

