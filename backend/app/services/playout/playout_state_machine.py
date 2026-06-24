from __future__ import annotations

from app.services.playout.dynamic_errors import DynamicPlayoutError


class PlayoutStateMachine:
    _allowed: dict[str, set[str]] = {
        "stopped": {"starting", "failed"},
        "starting": {"idle", "stopping", "failed"},
        "idle": {"playing_talking", "stopping", "failed"},
        "playing_talking": {"idle", "stopping", "failed"},
        "stopping": {"stopped", "failed"},
        "failed": {"starting", "stopped"},
    }

    def assert_transition(self, current: str, target: str, *, force: bool = False) -> None:
        if current == target:
            return
        if force and target in {"stopping", "stopped", "failed"}:
            return
        if target not in self._allowed.get(current, set()):
            raise DynamicPlayoutError(
                "playout_session_not_stoppable",
                f"invalid playout state transition: {current} -> {target}",
            )


playout_state_machine = PlayoutStateMachine()

