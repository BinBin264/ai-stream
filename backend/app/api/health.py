from fastapi import APIRouter

from app.core.config import settings
from app.services.store import store

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "live_sessions": len(store.live_sessions),
        "comments": len(store.comments),
        "jobs": len(store.jobs),
        "products": len(store.products),
        "variants": len(store.variants),
        "orders": len(store.orders),
        "active_reservations": len(store.reservations),
    }
