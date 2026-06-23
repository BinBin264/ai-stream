from __future__ import annotations

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued":            frozenset({"generating_audio", "cancelled", "failed"}),
    "generating_audio":  frozenset({"rendering", "failed", "cancelled"}),
    "rendering":         frozenset({"downloading", "failed", "cancelled"}),
    "downloading":       frozenset({"completed", "failed", "cancelled"}),
    "completed":         frozenset(),
    "failed":            frozenset({"queued"}),    # queued = retry path
    "cancelled":         frozenset(),
}


class InvalidStatusTransitionError(ValueError):
    pass


class RenderStatusService:
    def validate_transition(self, current: str, next_status: str) -> None:
        allowed = VALID_TRANSITIONS.get(current, frozenset())
        if next_status not in allowed:
            raise InvalidStatusTransitionError(
                f"Cannot transition {current!r} → {next_status!r}. "
                f"Allowed: {sorted(allowed) or 'none (terminal)'}"
            )

    def can_cancel(self, status: str) -> bool:
        return "cancelled" in VALID_TRANSITIONS.get(status, frozenset())

    def is_terminal(self, status: str) -> bool:
        return len(VALID_TRANSITIONS.get(status, frozenset())) == 0


render_status_service = RenderStatusService()
