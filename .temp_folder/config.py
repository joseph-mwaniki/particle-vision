from __future__ import annotations

from dataclasses import dataclass, fields
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
    batch_size: int = 32
    max_batch_size: int = 128
    workers: int = 0
    max_memory_mb: int = 0
    estimated_mb_per_worker: int = 180
    serial_frame_threshold: int = 64
    progress_min_delta: int = 1
    adaptive_blur: bool = True
    min_blur_threshold: float = 20.0
    sampling_stride: int = 5
    max_frame_gap: int = 25
    continuity_aware: bool = True
    conservative_redundancy: bool = True
    experimental_uniform_sampling: bool = False
    experimental_interval_seconds: float = 2.5
    experimental_start_seconds: float = 3.0
    radical_uniform_sampling: bool = True
    radical_interval_seconds: float = 3.0
    radical_start_seconds: float = 3.0

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
            "batch_size": self.batch_size,
            "max_batch_size": self.max_batch_size,
            "workers": self.workers,
            "max_memory_mb": self.max_memory_mb,
            "estimated_mb_per_worker": self.estimated_mb_per_worker,
            "serial_frame_threshold": self.serial_frame_threshold,
            "progress_min_delta": self.progress_min_delta,
            "adaptive_blur": self.adaptive_blur,
            "min_blur_threshold": self.min_blur_threshold,
            "sampling_stride": self.sampling_stride,
            "max_frame_gap": self.max_frame_gap,
            "continuity_aware": self.continuity_aware,
            "conservative_redundancy": self.conservative_redundancy,
            "experimental_uniform_sampling": self.experimental_uniform_sampling,
            "experimental_interval_seconds": self.experimental_interval_seconds,
            "experimental_start_seconds": self.experimental_start_seconds,
            "radical_uniform_sampling": self.radical_uniform_sampling,
            "radical_interval_seconds": self.radical_interval_seconds,
            "radical_start_seconds": self.radical_start_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelectorConfig":
        values = dict(data)
        aliases = {
            "sample_stride": "sampling_stride",
            "max_source_frame_gap": "max_frame_gap",
            "enforce_continuity": "continuity_aware",
        }
        for alias, field_name in aliases.items():
            if alias in values and field_name not in values:
                values[field_name] = values[alias]
        valid_fields = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in valid_fields})
