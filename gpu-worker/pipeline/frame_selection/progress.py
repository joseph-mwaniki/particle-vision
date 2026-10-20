"""Throttle high-frequency progress emissions to reduce callback amplification."""

from __future__ import annotations

import time

_STAGE_BOUNDARY_MARKERS = (
    "starting",
    "complete",
    "export complete",
    "coverage validation",
)


class ProgressThrottler:
    """Emit progress only when enough time and percent have elapsed.

    Always emits the first update, forced updates, and 100%.
    """

    def __init__(self, min_interval: float = 2.0, min_pct_delta: float = 1.0) -> None:
        self.min_interval = min_interval
        self.min_pct_delta = min_pct_delta
        self.last_time = 0.0
        self.last_pct = -1.0

    def should_emit(self, pct: float, force: bool = False) -> bool:
        if force or pct >= 100:
            self.last_time = time.time()
            self.last_pct = pct
            return True

        now = time.time()
        if self.last_pct < 0:
            self.last_time = now
            self.last_pct = pct
            return True

        if now - self.last_time >= self.min_interval and pct - self.last_pct >= self.min_pct_delta:
            self.last_time = now
            self.last_pct = pct
            return True
        return False


def is_stage_boundary_message(message: str) -> bool:
    lower = message.lower()
    return any(marker in lower for marker in _STAGE_BOUNDARY_MARKERS)
