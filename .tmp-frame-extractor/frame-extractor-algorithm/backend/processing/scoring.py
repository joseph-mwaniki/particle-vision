from __future__ import annotations

from backend.models.frame import FrameMetrics
from backend.processing.config import SelectorConfig


def compute_frame_score(frame: FrameMetrics, config: SelectorConfig) -> float:
    sharpness_score = min(1.0, frame.sharpness / max(config.blur_threshold * 1.5, 1.0))
    brightness_score = 1.0 - min(1.0, abs(frame.brightness - 128.0) / 128.0)
    exposure_score = 1.0 if frame.exposure_label == "good" else 0.15
    viewpoint_score = max(0.0, frame.viewpoint_change_score)
    redundancy_penalty = max(0.0, frame.redundancy_score)
    score = (
        sharpness_score * 0.45
        + brightness_score * 0.20
        + exposure_score * 0.25
        + viewpoint_score * 0.25
        - redundancy_penalty * 0.35
    )
    return max(0.0, min(1.0, score))
