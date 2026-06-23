from fastapi import APIRouter

from app.models.domain import CommentStatus, ConversationStatus, OrderStatus, ReservationStatus
from app.services.media.publisher import media_publisher
from app.services.media.render_orchestrator import DEMO_TENANT_ID, media_render_orchestrator
from app.services.store import store

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/live-dashboard")
async def live_dashboard() -> dict:
    render_jobs = await media_render_orchestrator.list_render_jobs(DEMO_TENANT_ID, limit=500)
    speech_items = await media_publisher.list_items(DEMO_TENANT_ID, limit=500)
    return {
        "live_sessions": len(store.live_sessions),
        "comments": len(store.comments),
        "queued_comments": len([item for item in store.comments.values() if item.status == CommentStatus.QUEUED]),
        "orders": len(store.orders),
        "stock_reserved_orders": len([item for item in store.orders.values() if item.status == OrderStatus.STOCK_RESERVED]),
        "active_reservations": len(
            [item for item in store.reservations.values() if item.status == ReservationStatus.ACTIVE]
        ),
        "human_handover": len(
            [item for item in store.conversations.values() if item.status == ConversationStatus.HUMAN_TAKEOVER]
        ),
        "failed_comments": len([item for item in store.comments.values() if item.status == CommentStatus.FAILED]),
        "speech_queue": len(speech_items),
        "media_render_jobs": len(render_jobs),
        "media_render_failed": len([item for item in render_jobs if item.get("status") == "failed"]),
    }


@router.get("/failures")
async def list_failures() -> dict:
    return {
        "comments": [item for item in store.comments.values() if item.status == CommentStatus.FAILED],
        "webhooks": [item for item in store.webhook_events.values() if item.status == "failed"],
    }


@router.get("/live-sessions/{live_id}/metrics")
async def live_metrics(live_id: str) -> dict:
    comments = [item for item in store.comments.values() if item.live_id == live_id]
    orders = [item for item in store.orders.values() if item.live_session_id == live_id]
    return {
        "live_id": live_id,
        "comments": len(comments),
        "answered_comments": len([item for item in comments if item.status == CommentStatus.ANSWERED]),
        "orders": len(orders),
        "reserved_revenue_vnd": sum(order.total_vnd for order in orders if order.status == OrderStatus.STOCK_RESERVED),
    }
