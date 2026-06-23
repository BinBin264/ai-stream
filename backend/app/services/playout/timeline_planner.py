from __future__ import annotations

from app.services.playout.errors import PLAYOUT_DURATION_OVERFLOW, PlayoutError
from app.services.playout.schemas import PlayoutManifest, SegmentValidation, TimelineItem, TimelinePlan


class TimelinePlanner:
    def plan(
        self,
        manifest: PlayoutManifest,
        *,
        idle_source_path: str,
        talking_segments: list[SegmentValidation],
    ) -> TimelinePlan:
        durations = {segment.segment_id: segment.duration_seconds for segment in talking_segments}
        items: list[TimelineItem] = []
        warnings: list[str] = []
        cursor = 0.0
        sequence = 1

        def add(kind: str, segment_id: str, source_path: str, duration: float, priority: str | None = None) -> None:
            nonlocal cursor, sequence
            if duration <= 0:
                return
            start = round(cursor, 3)
            cursor += duration
            items.append(
                TimelineItem(
                    sequence=sequence,
                    kind=kind,  # type: ignore[arg-type]
                    segment_id=segment_id,
                    source_path=source_path,
                    start_seconds=start,
                    end_seconds=round(cursor, 3),
                    duration_seconds=round(duration, 3),
                    priority=priority,  # type: ignore[arg-type]
                )
            )
            sequence += 1

        add("idle", "idle_lead", idle_source_path, manifest.idle_lead_seconds)
        for index, segment in enumerate(manifest.talking_segments):
            duration = durations.get(segment.segment_id)
            if duration is None:
                raise PlayoutError(PLAYOUT_DURATION_OVERFLOW, f"missing duration for segment {segment.segment_id}")
            add("talking", segment.segment_id, segment.source_path, duration, segment.priority)
            idle_duration = manifest.idle_between_seconds
            if index == len(manifest.talking_segments) - 1:
                idle_duration = max(idle_duration, manifest.idle_tail_minimum_seconds)
            add("idle", f"idle_after_{segment.segment_id}", idle_source_path, idle_duration)

        if cursor < manifest.target_duration_seconds:
            fill = manifest.target_duration_seconds - cursor
            if items and items[-1].kind == "idle":
                last = items[-1]
                last.duration_seconds = round(last.duration_seconds + fill, 3)
                last.end_seconds = round(manifest.target_duration_seconds, 3)
                cursor = manifest.target_duration_seconds
            else:
                add("idle", "idle_fill", idle_source_path, fill)
        elif cursor > manifest.target_duration_seconds:
            warnings.append("planned content exceeds target duration; output duration was extended")

        mandatory_without_fill = manifest.idle_lead_seconds + sum(durations.values())
        mandatory_without_fill += manifest.idle_between_seconds * max(len(manifest.talking_segments) - 1, 0)
        mandatory_without_fill += manifest.idle_tail_minimum_seconds
        if manifest.target_duration_seconds < mandatory_without_fill:
            raise PlayoutError(
                PLAYOUT_DURATION_OVERFLOW,
                "target duration is shorter than mandatory talking content and required idle",
            )

        return TimelinePlan(
            program_id=manifest.program_id,
            avatar_id=manifest.avatar_id,
            target_duration_seconds=manifest.target_duration_seconds,
            planned_duration_seconds=round(cursor, 3),
            transition=manifest.transition,
            items=items,
            warnings=warnings,
        )

