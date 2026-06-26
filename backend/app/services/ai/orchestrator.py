from __future__ import annotations

import logging

from app.core.config import settings
from app.models.domain import LiveComment, ResponseJob
from app.services.ai.gemini_client import gemini_client

logger = logging.getLogger(__name__)


class AiOrchestrator:
    """Turns a comment into an answer and a media segment."""

    async def create_response_job(self, comment: LiveComment) -> ResponseJob:
        prompt = f"Viewer {comment.user_name} asked: {comment.text}"
        return ResponseJob(live_id=comment.live_id, comment_id=comment.id, prompt=prompt)

    async def answer_text(self, comment: LiveComment) -> str:
        if settings.GEMINI_ENABLED and settings.GEMINI_API_KEY:
            try:
                prompt = f'Khách hàng {comment.user_name} bình luận: "{comment.text}"'
                return await gemini_client.generate(prompt)
            except Exception:
                logger.warning("Gemini answer_text failed, using fallback")
        return f"{comment.user_name}, mình đã nhận câu hỏi. Tư vấn viên sẽ hỗ trợ ngay ạ."

    async def request_avatar_segment(self, text: str) -> str | None:
        if not settings.AI_AVATAR_BASE_URL:
            return None
        import httpx
        async with httpx.AsyncClient(timeout=120) as client:
            await client.get(f"{settings.AI_AVATAR_BASE_URL.rstrip('/')}/health")
        return None


ai_orchestrator = AiOrchestrator()
