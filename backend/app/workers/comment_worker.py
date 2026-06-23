import asyncio
import logging

from app.models.domain import CommentStatus
from app.services.comments.repository import live_comment_repository
from app.services.ai.orchestrator import ai_orchestrator
from app.services.commerce.service import commerce_pipeline
from app.services.queue.comment_queue import comment_queue
from app.services.realtime import realtime_hub
from app.services.store import store

logger = logging.getLogger(__name__)


async def run_comment_worker() -> None:
    """Continuously turn queued comments into response jobs.

    This is intentionally not auto-started in the API process yet. Run it as a
    separate worker once Redis/Postgres repositories replace the in-memory MVP.
    """
    while True:
        comment = await comment_queue.get()
        comment.status = CommentStatus.PROCESSING
        store.save_comment(comment)
        await live_comment_repository.update_from_domain(comment, tenant_id=comment.tenant_id)
        await realtime_hub.broadcast(comment.live_id, {"type": "comment_updated", "comment": comment.model_dump()})
        try:
            job = await ai_orchestrator.create_response_job(comment)
            job.status = "processing"
            store.save_job(job)
            await realtime_hub.broadcast(comment.live_id, {"type": "job_updated", "job": job.model_dump()})

            result = await commerce_pipeline.process_comment(comment)
            job.response_text = result.reply_text
            job.status = "commerce_processed"
            store.save_job(job)
            store.save_comment(result.comment)
            await live_comment_repository.mark_answered(
                result.comment.id,
                ai_reply=result.reply_text,
                status=str(result.comment.status),
                tenant_id=result.comment.tenant_id,
            )
            await realtime_hub.broadcast(comment.live_id, {"type": "job_updated", "job": job.model_dump()})
            await comment_queue.ack_comment(comment.id)
        except Exception as exc:
            logger.exception("Failed to process comment %s", comment.id)
            comment.status = CommentStatus.FAILED
            store.save_comment(comment)
            await live_comment_repository.update_from_domain(comment, tenant_id=comment.tenant_id)
            await realtime_hub.broadcast(
                comment.live_id,
                {"type": "worker_error", "comment_id": comment.id, "error": str(exc)},
            )


if __name__ == "__main__":
    asyncio.run(run_comment_worker())
