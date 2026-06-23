from app.services.director.action_models import LiveDirectorAction
from app.services.director.product_queue import product_queue_service
from app.services.media.publisher import DEMO_TENANT_ID


class LiveDirector:
    async def prepare_live(self, live_id: str, tenant_id: str = DEMO_TENANT_ID) -> dict:
        return await product_queue_service.prepare(live_id=live_id, tenant_id=tenant_id)

    def present_segment_action(self, segment: dict) -> LiveDirectorAction:
        return LiveDirectorAction(
            action_type="present_segment",
            speech_text=segment["speech_text"],
            priority="P4",
            motion_code=segment.get("motion_code") or "talk_calm",
            overlay=segment.get("overlay_json") or {},
            resume_cursor=str(segment["id"]),
        )

    def answer_comment_action(
        self,
        *,
        speech_text: str,
        priority: str = "P2",
        motion_code: str = "talk_calm",
        overlay: dict | None = None,
        resume_cursor: str | None = None,
    ) -> LiveDirectorAction:
        return LiveDirectorAction(
            action_type="answer_comment",
            speech_text=speech_text,
            priority=priority,
            motion_code=motion_code,
            overlay=overlay or {},
            resume_cursor=resume_cursor,
        )


live_director = LiveDirector()
