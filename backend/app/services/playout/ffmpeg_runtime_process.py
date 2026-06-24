from __future__ import annotations

from app.services.playout.local_preview_sink import LocalPreviewSink
from app.services.playout.playout_output_sink import PlayoutOutputSink


def make_output_sink(output_mode: str) -> PlayoutOutputSink:
    if output_mode in {"local_preview", "file_output"}:
        return LocalPreviewSink()
    raise ValueError(f"Unsupported playout output mode: {output_mode}")

