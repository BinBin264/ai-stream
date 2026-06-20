from fastapi import APIRouter, HTTPException

from app.models.domain import ResponseJob
from app.services.ai.orchestrator import ai_orchestrator
from app.services.commerce.service import commerce_pipeline
from app.services.realtime import realtime_hub
from app.services.store import store

router = APIRouter(prefix="/api/comments", tags=["comments"])


@router.get("/live/{live_id}")
async def list_comments(live_id: str) -> dict:
    return {"items": store.list_comments(live_id)}


@router.post("/{comment_id}/answer")
async def answer_comment(comment_id: str) -> dict:
    comment = store.comments.get(comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    job: ResponseJob = await ai_orchestrator.create_response_job(comment)
    result = await commerce_pipeline.process_comment(comment)
    job.response_text = result.reply_text
    job.status = "commerce_processed"
    store.save_job(job)
    await realtime_hub.broadcast(comment.live_id, {"type": "comment_updated", "comment": result.comment.model_dump()})
    await realtime_hub.broadcast(comment.live_id, {"type": "job_updated", "job": job.model_dump()})
    return {"job": job, "pipeline": result}
