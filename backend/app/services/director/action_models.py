from typing import Literal

from pydantic import BaseModel, Field

LiveActionType = Literal[
    "present_segment",
    "answer_comment",
    "confirm_order",
    "show_product",
    "show_order",
    "idle",
    "resume_segment",
    "next_product",
    "end_live",
]


class LiveDirectorAction(BaseModel):
    action_type: LiveActionType
    speech_text: str = ""
    priority: str = "P4"
    motion_code: str = "talk_calm"
    overlay: dict = Field(default_factory=dict)
    resume_cursor: str | None = None
