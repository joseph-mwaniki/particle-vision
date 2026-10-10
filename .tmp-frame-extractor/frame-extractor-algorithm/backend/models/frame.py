from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FrameMetrics:
    frame_index: int
    timestamp: float
    sharpness: float = 0.0
    brightness: float = 0.0
    dark_ratio: float = 0.0
    bright_ratio: float = 0.0
    similarity: float = 1.0
    status: str = "pending"
    reason: str = ""
    final_score: float = 0.0
    sharpness_score: float = 0.0
    exposure_score: float = 0.0
    viewpoint_change_score: float = 0.0
    redundancy_score: float = 0.0
    quality_label: str = "unknown"
    exposure_label: str = "unknown"
    selected: bool = False
    in_window: int = 0
    image: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp": round(self.timestamp, 6),
            "sharpness": round(self.sharpness, 3),
            "brightness": round(self.brightness, 3),
            "dark_ratio": round(self.dark_ratio, 4),
            "bright_ratio": round(self.bright_ratio, 4),
            "similarity": round(self.similarity, 4),
            "status": self.status,
            "reason": self.reason,
            "final_score": round(self.final_score, 4),
            "sharpness_score": round(self.sharpness_score, 4),
            "exposure_score": round(self.exposure_score, 4),
            "viewpoint_change_score": round(self.viewpoint_change_score, 4),
            "redundancy_score": round(self.redundancy_score, 4),
            "quality_label": self.quality_label,
            "exposure_label": self.exposure_label,
            "selected": self.selected,
            "in_window": self.in_window,
            "metadata": self.metadata,
        }
