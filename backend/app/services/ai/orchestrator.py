import httpx

from app.core.config import settings
from app.models.domain import LiveComment, ResponseJob


class AiOrchestrator:
    """Turns a comment into an answer and a media segment."""

    async def create_response_job(self, comment: LiveComment) -> ResponseJob:
        prompt = f"Viewer {comment.user_name} asked: {comment.text}"
        return ResponseJob(live_id=comment.live_id, comment_id=comment.id, prompt=prompt)

    async def answer_text(self, comment: LiveComment) -> str:
        # TODO: call ai-avatar-system or local LLM service.
        return f"{comment.user_name}, mình đã nhận câu hỏi của bạn: {comment.text}"

    async def request_avatar_segment(self, text: str) -> str | None:
        # TODO: replace with a dedicated ai-avatar-system REST endpoint.
        if not settings.AI_AVATAR_BASE_URL:
            return None
        async with httpx.AsyncClient(timeout=120) as client:
            await client.get(f"{settings.AI_AVATAR_BASE_URL.rstrip('/')}/health")
        return None


ai_orchestrator = AiOrchestrator()
