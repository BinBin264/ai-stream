from fastapi import APIRouter

from app.api.live import CreateLiveRequest, create_live_session, delete_live_session, get_live_session, go_live, list_live_sessions, start_live, stop_live

router = APIRouter(prefix="/api/live-sessions", tags=["live-sessions"])


router.add_api_route("", list_live_sessions, methods=["GET"])
router.add_api_route("", create_live_session, methods=["POST"])
router.add_api_route("/{live_id}", get_live_session, methods=["GET"])
router.add_api_route("/{live_id}", delete_live_session, methods=["DELETE"])
router.add_api_route("/{live_id}/start", start_live, methods=["POST"])
router.add_api_route("/{live_id}/go-live", go_live, methods=["POST"])
router.add_api_route("/{live_id}/end", stop_live, methods=["POST"])
router.add_api_route("/{live_id}/status", get_live_session, methods=["GET"])

__all__ = ["CreateLiveRequest", "router"]
