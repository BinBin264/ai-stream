from __future__ import annotations

from typing import Literal

PlayoutSessionStatus = Literal[
    "stopped",
    "starting",
    "idle",
    "playing_talking",
    "stopping",
    "failed",
]

PlayoutOutputMode = Literal["local_preview", "file_output"]

