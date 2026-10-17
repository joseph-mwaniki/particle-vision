from __future__ import annotations

import cv2
import numpy as np


def prepare_similarity_frame(frame_or_gray: np.ndarray, max_size: tuple[int, int] = (64, 64)) -> np.ndarray:
    if frame_or_gray.shape == max_size and frame_or_gray.dtype == np.float32:
        return frame_or_gray
    if frame_or_gray.ndim == 3:
        gray = cv2.cvtColor(frame_or_gray, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame_or_gray
    resized = cv2.resize(gray, max_size, interpolation=cv2.INTER_AREA)
    return resized.astype(np.float32)


def compute_similarity(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    a = (
        frame_a
        if (frame_a.shape == (64, 64) and frame_a.dtype == np.float32)
        else prepare_similarity_frame(frame_a)
    )
    b = (
        frame_b
        if (frame_b.shape == (64, 64) and frame_b.dtype == np.float32)
        else prepare_similarity_frame(frame_b)
    )
    diff = np.abs(a - b)
    normalized = 1.0 - (diff.mean() / 255.0)
    return float(np.clip(normalized, 0.0, 1.0))



def perceptual_hash(frame: np.ndarray, hash_size: int = 8) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(resized.astype(np.float32))
    low = dct[:hash_size, :hash_size]
    mean = float(low.mean())
    bits = (low > mean).astype(np.uint8).reshape(-1)
    return bits
