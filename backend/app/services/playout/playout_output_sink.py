from __future__ import annotations

from pathlib import Path


class PlayoutOutputSink:
    async def start(self, session_id: str) -> str:
        raise NotImplementedError

    async def append_idle(self, *, source_path: Path, duration_seconds: int) -> None:
        raise NotImplementedError

    async def append_talking(self, *, source_path: Path) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    def is_alive(self) -> bool:
        return False

    def last_output_update_at(self):
        return None

