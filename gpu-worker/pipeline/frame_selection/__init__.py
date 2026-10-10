"""Gaussian-splat frame selection algorithm (CPU).

Vendored from the tested frame-extractor-algorithm implementation.
"""

from .config import SelectorConfig
from .frame_selector import evaluate_temporal_bridge, select_frames

__all__ = [
    "SelectorConfig",
    "evaluate_temporal_bridge",
    "select_frames",
]
