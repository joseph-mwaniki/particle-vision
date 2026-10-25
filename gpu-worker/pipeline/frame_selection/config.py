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
    adaptive_blur: bool = True
    min_blur_threshold: float = 20.0
    sampling_stride: int = 5
    max_frame_gap: int = 25
    continuity_aware: bool = True
    conservative_redundancy: bool = True

    def __init__(
        self,
        blur_threshold: float = 80.0,
        exposure_dark_threshold: float = 0.12,
        exposure_bright_threshold: float = 0.12,
        min_brightness: float = 18.0,
        max_brightness: float = 240.0,
        window_seconds: float = 1.0,
        min_frames_per_window: int = 2,
        max_frames_per_window: int = 10,
        similarity_threshold: float = 0.88,
        bridge_similarity_threshold: float = 0.9,
        bridge_overlap_threshold: float = 0.55,
        feature_match_threshold: float = 0.7,
        min_feature_matches: int = 30,
        lookahead_window: int = 3,
        min_viewpoint_change: float = 0.15,
        transition_protection_threshold: float = 0.65,
        max_rejected_preview: int = 50,
        coverage_gap_seconds: float = 2.5,
        frame_resize_width: int = 320,
        frame_resize_height: int = 180,
        max_analysis_frames: int | None = None,
        min_final_selection: int = 8,
        adaptive_blur: bool = True,
        min_blur_threshold: float = 20.0,
        sampling_stride: int = 5,
        max_frame_gap: int = 25,
        continuity_aware: bool = True,
        conservative_redundancy: bool = True,
        **kwargs: Any,
    ):
        if "sample_stride" in kwargs:
            sampling_stride = kwargs["sample_stride"]
        if "max_source_frame_gap" in kwargs:
            max_frame_gap = kwargs["max_source_frame_gap"]
        if "enforce_continuity" in kwargs:
            continuity_aware = kwargs["enforce_continuity"]

        self.blur_threshold = blur_threshold
        self.exposure_dark_threshold = exposure_dark_threshold
        self.exposure_bright_threshold = exposure_bright_threshold
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.window_seconds = window_seconds
        self.min_frames_per_window = min_frames_per_window
        self.max_frames_per_window = max_frames_per_window
        self.similarity_threshold = similarity_threshold
        self.bridge_similarity_threshold = bridge_similarity_threshold
        self.bridge_overlap_threshold = bridge_overlap_threshold
        self.feature_match_threshold = feature_match_threshold
        self.min_feature_matches = min_feature_matches
        self.lookahead_window = lookahead_window
        self.min_viewpoint_change = min_viewpoint_change
        self.transition_protection_threshold = transition_protection_threshold
        self.max_rejected_preview = max_rejected_preview
        self.coverage_gap_seconds = coverage_gap_seconds
        self.frame_resize_width = frame_resize_width
        self.frame_resize_height = frame_resize_height
        self.max_analysis_frames = max_analysis_frames
        self.min_final_selection = min_final_selection
        self.adaptive_blur = adaptive_blur
        self.min_blur_threshold = min_blur_threshold
        self.sampling_stride = sampling_stride
        self.max_frame_gap = max_frame_gap
        self.continuity_aware = continuity_aware
        self.conservative_redundancy = conservative_redundancy

    @property
    def sample_stride(self) -> int:
        return self.sampling_stride

    @sample_stride.setter
    def sample_stride(self, val: int) -> None:
        self.sampling_stride = val

    @property
    def max_source_frame_gap(self) -> int:
        return self.max_frame_gap

    @max_source_frame_gap.setter
    def max_source_frame_gap(self, val: int) -> None:
        self.max_frame_gap = val

    @property
    def enforce_continuity(self) -> bool:
        return self.continuity_aware

    @enforce_continuity.setter
    def enforce_continuity(self, val: bool) -> None:
        self.continuity_aware = val

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
            "adaptive_blur": self.adaptive_blur,
            "min_blur_threshold": self.min_blur_threshold,
            "sampling_stride": self.sampling_stride,
            "max_frame_gap": self.max_frame_gap,
            "continuity_aware": self.continuity_aware,
            "conservative_redundancy": self.conservative_redundancy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelectorConfig":
        d = dict(data)
        if "sample_stride" in d and "sampling_stride" not in d:
            d["sampling_stride"] = d["sample_stride"]
        if "max_source_frame_gap" in d and "max_frame_gap" not in d:
            d["max_frame_gap"] = d["max_source_frame_gap"]
        if "enforce_continuity" in d and "continuity_aware" not in d:
            d["continuity_aware"] = d["enforce_continuity"]
        field_names = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in d.items() if key in field_names})
