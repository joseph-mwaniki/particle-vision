from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SelectorConfig:
    blur_threshold: float = 80.0
    exposure_dark_threshold: float = 0.12
    exposure_bright_threshold: float = 0.12
    min_brightness: float = 18.0
    max_brightness: float = 240.0
    window_seconds: float = 1.0
    min_frames_per_window: int = 2
    max_frames_per_window: int = 10
    similarity_threshold: float = 0.88
    bridge_similarity_threshold: float = 0.9
    bridge_overlap_threshold: float = 0.55
    feature_match_threshold: float = 0.7
    min_feature_matches: int = 30
    lookahead_window: int = 3
    min_viewpoint_change: float = 0.15
    transition_protection_threshold: float = 0.65
    max_rejected_preview: int = 50
    coverage_gap_seconds: float = 2.5
    frame_resize_width: int = 320
    frame_resize_height: int = 180
    max_analysis_frames: int | None = None
    min_final_selection: int = 8

    def to_dict(self) -> dict[str, Any]:
        return {
            "blur_threshold": self.blur_threshold,
            "exposure_dark_threshold": self.exposure_dark_threshold,
            "exposure_bright_threshold": self.exposure_bright_threshold,
            "min_brightness": self.min_brightness,
            "max_brightness": self.max_brightness,
            "window_seconds": self.window_seconds,
            "min_frames_per_window": self.min_frames_per_window,
            "max_frames_per_window": self.max_frames_per_window,
            "similarity_threshold": self.similarity_threshold,
            "bridge_similarity_threshold": self.bridge_similarity_threshold,
            "bridge_overlap_threshold": self.bridge_overlap_threshold,
            "feature_match_threshold": self.feature_match_threshold,
            "min_feature_matches": self.min_feature_matches,
            "lookahead_window": self.lookahead_window,
            "min_viewpoint_change": self.min_viewpoint_change,
            "transition_protection_threshold": self.transition_protection_threshold,
            "coverage_gap_seconds": self.coverage_gap_seconds,
            "frame_resize_width": self.frame_resize_width,
            "frame_resize_height": self.frame_resize_height,
            "max_analysis_frames": self.max_analysis_frames,
            "min_final_selection": self.min_final_selection,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelectorConfig":
        return cls(**{key: value for key, value in data.items() if hasattr(cls, key)})
