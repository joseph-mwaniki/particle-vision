"""Gaussian-splat frame selection algorithm (CPU).

Vendored from the tested frame-extractor-algorithm implementation.
"""

from .config import SelectorConfig
from .frame_selector import enforce_continuity, evaluate_temporal_bridge, select_frames

__all__ = [
    "SelectorConfig",
    "enforce_continuity",
    "evaluate_temporal_bridge",
    "select_frames",
]
