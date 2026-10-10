from __future__ import annotations

import cv2
import numpy as np


def variance_of_laplacian(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def classify_blur(sharpness: float, blur_threshold: float) -> str:
    if sharpness >= blur_threshold * 1.15:
        return "sharp"
    if sharpness >= blur_threshold * 0.8:
        return "slightly_blurred"
    return "blurry"
