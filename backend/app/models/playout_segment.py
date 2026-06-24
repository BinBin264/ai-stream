from __future__ import annotations

from typing import Literal

PlayoutSegmentType = Literal["talking"]
PlayoutSegmentStatus = Literal["queued", "ready", "playing", "completed", "cancelled", "failed"]
PlayoutPriority = Literal["P0", "P1", "P2", "P3", "P4"]

PRIORITY_RANK: dict[str, int] = {
    "P0": 100,
    "P1": 90,
    "P2": 80,
    "P3": 60,
    "P4": 40,
}

