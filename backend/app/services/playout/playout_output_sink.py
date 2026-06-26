from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class PlaybackReceipt:
    output_path: str
    duration_seconds: float
    started_at: datetime
    appended_at: datetime
    sequence_number: int


class PlayoutOutputSink:
    async def start(self, session_id: str) -> str:
        raise NotImplementedError

    async def append_idle(self, *, source_path: Path, duration_seconds: int) -> PlaybackReceipt:
        raise NotImplementedError

    async def append_talking(self, *, source_path: Path) -> PlaybackReceipt:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    def is_alive(self) -> bool:
        return False

    def last_output_update_at(self):
        return None
