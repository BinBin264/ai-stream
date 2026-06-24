from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.dynamic_playout import (
    CreatePlayoutSessionRequest,
    EnqueueTalkingSegmentRequest,
    PlayoutHealthResponse,
    PlayoutSegmentListResponse,
    PlayoutSegmentResponse,
    PlayoutSessionListResponse,
    PlayoutSessionResponse,
    PlayoutStatusResponse,
    StopPlayoutSessionRequest,
    SubmitPlayoutScriptRequest,
    SubmitPlayoutScriptResponse,
)
from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.playout_segment_queue import playout_segment_queue
from app.services.playout.playout_segment_service import playout_segment_service
from app.services.playout.playout_session_service import playout_session_service
from app.services.playout.runtime_health_service import runtime_health_service

router = APIRouter(prefix="/api/playout-sessions", tags=["playout-sessions"])


def _session_response(row: dict) -> PlayoutSessionResponse:
    return PlayoutSessionResponse(
        session_id=str(row["id"]),
        avatar_id=row["avatar_id"],
        live_session_id=row.get("live_session_id"),
        status=row["status"],
        output_mode=row["output_mode"],
        idle_video_path=row["idle_video_path"],
        output_path=row.get("output_path"),
        active_segment_id=str(row["active_segment_id"]) if row.get("active_segment_id") else None,
        started_at=row.get("started_at"),
        stopped_at=row.get("stopped_at"),
        last_heartbeat_at=row.get("last_heartbeat_at"),
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _segment_response(row: dict) -> PlayoutSegmentResponse:
    return PlayoutSegmentResponse(
        segment_id=str(row["id"]),
        playout_session_id=str(row["playout_session_id"]),
        avatar_render_job_id=str(row["avatar_render_job_id"]) if row.get("avatar_render_job_id") else None,
        source_video_path=row.get("source_video_path"),
        segment_type=row["segment_type"],
        priority=row["priority"],
        status=row["status"],
        queue_position=row["queue_position"],
        requested_at=row["requested_at"],
        queued_at=row.get("queued_at"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        cancelled_at=row.get("cancelled_at"),
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _raise(exc: DynamicPlayoutError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_dict())


@router.post("", response_model=PlayoutSessionResponse, status_code=201)
async def create_playout_session(body: CreatePlayoutSessionRequest) -> PlayoutSessionResponse:
    try:
        row = await playout_session_service.create(
            avatar_id=body.avatar_id,
            live_session_id=body.live_session_id,
            output_mode=body.output_mode,
        )
    except DynamicPlayoutError as exc:
        _raise(exc)
    return _session_response(row)


@router.get("", response_model=PlayoutSessionListResponse)
async def list_playout_sessions() -> PlayoutSessionListResponse:
    rows = await playout_session_service.list()
    return PlayoutSessionListResponse(items=[_session_response(row) for row in rows])


@router.get("/{session_id}", response_model=PlayoutSessionResponse)
async def get_playout_session(session_id: str) -> PlayoutSessionResponse:
    try:
        row = await playout_session_service.get(session_id)
    except DynamicPlayoutError as exc:
        _raise(exc)
    return _session_response(row)


@router.post("/{session_id}/start", response_model=PlayoutStatusResponse, status_code=202)
async def start_playout_session(session_id: str) -> PlayoutStatusResponse:
    try:
        session = await playout_session_service.get(session_id)
        if session["status"] in {"idle", "playing_talking", "starting"}:
            raise DynamicPlayoutError("playout_session_already_running", "playout session is already running", status_code=409)
        playout_session_service.idle_path_for(session["avatar_id"])
        row = await playout_session_service.transition(session_id, "starting")
        await playout_segment_queue.publish_control(session_id=session_id, action="start")
    except DynamicPlayoutError as exc:
        _raise(exc)
    return PlayoutStatusResponse(session_id=session_id, status=row["status"])


@router.post("/{session_id}/stop", response_model=PlayoutStatusResponse, status_code=202)
async def stop_playout_session(session_id: str, body: StopPlayoutSessionRequest | None = None) -> PlayoutStatusResponse:
    force = bool(body.force) if body else False
    try:
        row = await playout_session_service.request_stop(session_id, force=force)
        await playout_segment_queue.publish_control(session_id=session_id, action="stop", force=force)
    except DynamicPlayoutError as exc:
        _raise(exc)
    return PlayoutStatusResponse(session_id=session_id, status=row["status"])


@router.post("/{session_id}/scripts", response_model=SubmitPlayoutScriptResponse, status_code=202)
async def submit_playout_script(session_id: str, body: SubmitPlayoutScriptRequest) -> SubmitPlayoutScriptResponse:
    try:
        job, segment = await playout_segment_service.submit_script(
            session_id=session_id,
            text=body.text,
            priority=body.priority,
            voice_id=body.voice_id,
            idempotency_key=body.idempotency_key,
        )
    except DynamicPlayoutError as exc:
        _raise(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SubmitPlayoutScriptResponse(
        render_job_id=str(job["id"]),
        playout_segment_id=str(segment["id"]),
        status="rendering",
        message="Avatar render job created. Segment will be queued after render completion.",
    )


@router.post("/{session_id}/segments", response_model=PlayoutSegmentResponse, status_code=202)
async def enqueue_playout_segment(session_id: str, body: EnqueueTalkingSegmentRequest) -> PlayoutSegmentResponse:
    try:
        row = await playout_segment_service.enqueue_existing_video(
            session_id=session_id,
            source_video_path=body.source_video_path,
            priority=body.priority,
            idempotency_key=body.idempotency_key,
        )
    except DynamicPlayoutError as exc:
        _raise(exc)
    return _segment_response(row)


@router.get("/{session_id}/segments", response_model=PlayoutSegmentListResponse)
async def list_playout_segments(session_id: str) -> PlayoutSegmentListResponse:
    try:
        await playout_session_service.get(session_id)
        rows = await playout_segment_service.list(session_id)
    except DynamicPlayoutError as exc:
        _raise(exc)
    return PlayoutSegmentListResponse(items=[_segment_response(row) for row in rows])


@router.post("/{session_id}/segments/{segment_id}/cancel", response_model=PlayoutSegmentResponse)
async def cancel_playout_segment(session_id: str, segment_id: str) -> PlayoutSegmentResponse:
    try:
        row = await playout_segment_service.cancel(session_id, segment_id)
    except DynamicPlayoutError as exc:
        _raise(exc)
    return _segment_response(row)


@router.get("/{session_id}/health", response_model=PlayoutHealthResponse)
async def get_playout_health(session_id: str) -> PlayoutHealthResponse:
    try:
        health = await runtime_health_service.health(session_id)
    except DynamicPlayoutError as exc:
        _raise(exc)
    return PlayoutHealthResponse(**health)
