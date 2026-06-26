import asyncio
import logging
import socket
from pathlib import Path

from app.core.config import settings
from app.services.media.publisher import DEMO_TENANT_ID, media_publisher
from app.services.media.render_orchestrator import media_render_orchestrator
from app.services.queue.redis_streams import redis_streams
from app.services.tts.client import get_tts_provider

logger = logging.getLogger(__name__)


class SpeechWorker:
    def __init__(self) -> None:
        self.consumer_name = f"speech-worker-{socket.gethostname()}"
        self.tts = get_tts_provider()

    async def run_forever(self) -> None:
        while True:
            messages = await redis_streams.read_group(
                stream=settings.STREAM_SPEECH,
                group=settings.REDIS_GROUP_SPEECH,
                consumer=self.consumer_name,
            )
            for _, stream_messages in messages:
                for message_id, payload in stream_messages:
                    await self.process_message(message_id, payload)

    async def process_message(self, message_id: str, payload: dict[str, str]) -> None:
        speech_item_id = payload["speech_item_id"]
        tenant_id = payload.get("tenant_id") or DEMO_TENANT_ID
        try:
            item = await media_publisher.mark_processing(speech_item_id, tenant_id=tenant_id)
            suffix = ".mp3" if settings.TTS_PROVIDER == "vietnamese" else ".wav"
            output_path = Path(settings.MEDIA_OUTPUT_DIR) / "audio" / f"{speech_item_id}{suffix}"
            voice_id = item["voice"] if item["voice"] != "default" else None
            result = await self.tts.synthesize(
                text=item["text"],
                voice_id=voice_id,
                output_path=str(output_path),
            )
            await media_publisher.mark_completed(speech_item_id, tenant_id=tenant_id, audio_url=result.audio_url)
            await media_render_orchestrator.create_render_job(
                tenant_id=tenant_id,
                live_session_id=str(item["live_session_id"]) if item["live_session_id"] else None,
                live_comment_id=str(item["live_comment_id"]) if item["live_comment_id"] else None,
                speech_queue_item_id=speech_item_id,
                input_text=item["text"],
                audio_url=result.audio_url,
                motion_code="talk_calm",
                overlay_json={},
                priority=item["priority"],
            )
            await redis_streams.ack(settings.STREAM_SPEECH, settings.REDIS_GROUP_SPEECH, message_id)
        except Exception as exc:
            logger.exception(
                "Failed to process speech item",
                extra={"speech_item_id": speech_item_id, "tenant_id": tenant_id},
            )
            try:
                await media_publisher.mark_failed(speech_item_id, str(exc), tenant_id=tenant_id)
            except Exception:
                logger.exception("Failed to mark speech item failed", extra={"speech_item_id": speech_item_id})


async def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL.upper())
    await SpeechWorker().run_forever()


if __name__ == "__main__":
    asyncio.run(main())
