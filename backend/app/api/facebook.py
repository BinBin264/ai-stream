import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.models.domain import WebhookEvent
from app.services.meta.client import meta_client
from app.services.meta.parser import parse_comment_events
from app.services.meta.webhook_security import webhook_security
from app.services.queue.comment_queue import comment_queue
from app.services.realtime import realtime_hub
from app.services.store import store

router = APIRouter(prefix="/api/facebook", tags=["facebook"])


@router.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> str:
    challenge = meta_client.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    if not challenge:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    return challenge


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    raw_body = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not webhook_security.verify_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid Meta webhook signature")

    try:
        payload = json.loads(raw_body.decode() or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed webhook payload") from exc

    payload_hash = webhook_security.payload_hash(raw_body)
    external_event_id = webhook_security.event_id_from_payload(payload, payload_hash)
    event, created = store.save_webhook_event(
        WebhookEvent(
            external_event_id=external_event_id,
            event_type="meta.page.webhook",
            page_id=str(payload.get("entry", [{}])[0].get("id", "")) or None,
            payload_json=payload,
            payload_hash=payload_hash,
        )
    )
    if not created:
        return {"received": True, "duplicate": True, "event_id": event.id, "comments": 0}

    default_live_id = payload.get("live_id") or "unknown-live"
    comments = parse_comment_events(payload, default_live_id=default_live_id)

    for comment in comments:
        existing = store.find_comment_by_external_id(comment.facebook_page_id, comment.external_comment_id)
        if existing:
            continue
        comment.raw_payload_reference = event.id
        store.save_comment(comment)
        await comment_queue.put(comment)
        await realtime_hub.broadcast(
            comment.live_id,
            {"type": "comment_created", "comment": comment.model_dump()},
        )

    return {
        "received": True,
        "duplicate": False,
        "event_id": event.id,
        "comments": len(comments),
        "verify_token_set": bool(settings.META_VERIFY_TOKEN),
    }


@router.post("/dev-comment")
async def create_dev_comment(payload: dict) -> dict:
    """Local test helper; replace with real Meta webhook events in production."""
    live_id = payload.get("live_id") or "unknown-live"
    event = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "live_id": live_id,
                            "id": payload.get("facebook_comment_id"),
                            "user_name": payload.get("user_name") or "Test Viewer",
                            "text": payload.get("text") or "Hello AI",
                        }
                    }
                ]
            }
        ]
    }
    comments = parse_comment_events(event, default_live_id=live_id)
    for comment in comments:
        store.save_comment(comment)
        await comment_queue.put(comment)
        await realtime_hub.broadcast(live_id, {"type": "comment_created", "comment": comment.model_dump()})
    return {"comments": comments}
