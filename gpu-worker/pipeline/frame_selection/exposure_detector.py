from __future__ import annotations

import numpy as np


def analyze_exposure(frame: np.ndarray) -> tuple[float, float, float, str]:
    gray = frame.mean(axis=2)
    brightness = float(gray.mean())
    dark_ratio = float(np.mean(gray < 30))
    bright_ratio = float(np.mean(gray > 245))

    if brightness < 70 and dark_ratio > 0.3:
        label = "too_dark"
    elif brightness > 180 and bright_ratio > 0.2:
        label = "too_bright"
    else:
        label = "good"

    return brightness, dark_ratio, bright_ratio, label
