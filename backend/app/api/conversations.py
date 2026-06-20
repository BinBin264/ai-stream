from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.store import store

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class TakeoverRequest(BaseModel):
    operator_id: str = "operator"


@router.get("")
async def list_conversations() -> dict:
    return {"items": sorted(store.conversations.values(), key=lambda item: item.updated_at, reverse=True)}


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict:
    conversation = store.conversations.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    comments = [
        comment
        for comment in store.comments.values()
        if comment.viewer_profile_id == conversation.viewer_profile_id and comment.live_id == conversation.live_session_id
    ]
    return {"conversation": conversation, "comments": comments}


@router.post("/{conversation_id}/takeover")
async def take_over_conversation(conversation_id: str, payload: TakeoverRequest) -> dict:
    conversation = store.take_over_conversation(conversation_id, payload.operator_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@router.post("/{conversation_id}/release-ai")
async def release_conversation_ai(conversation_id: str) -> dict:
    conversation = store.release_conversation_ai(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}
