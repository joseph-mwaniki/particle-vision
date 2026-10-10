from __future__ import annotations

from typing import Iterable

from .frame import FrameMetrics


def find_large_gaps(selected_frames: Iterable[FrameMetrics], gap_threshold: float) -> list[str]:
    ordered = sorted(selected_frames, key=lambda item: item.timestamp)
    gaps: list[str] = []
    for prev, curr in zip(ordered, ordered[1:]):
        delta = curr.timestamp - prev.timestamp
        if delta > gap_threshold:
            gaps.append(
                f"Large frame-selection gap detected between {prev.timestamp:.2f}s and {curr.timestamp:.2f}s."
            )
    return gaps
