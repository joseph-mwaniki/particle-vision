"""Optional process/system resource telemetry for frame selection."""

from __future__ import annotations

import logging
import os
import resource
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def rss_bytes() -> int | None:
    """Current process RSS in bytes, or None if unavailable."""
    try:
        # Linux: ru_maxrss is kilobytes; some platforms use bytes.
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if usage <= 0:
            return None
        # Heuristic: values under ~10M are almost certainly KiB on Linux.
        if usage < 10_000_000:
            return int(usage) * 1024
        return int(usage)
    except Exception:
        return None


def disk_usage(path: Path) -> dict[str, int] | None:
    try:
        usage = shutil.disk_usage(path)
        return {"total": usage.total, "used": usage.used, "free": usage.free}
    except Exception:
        return None


def directory_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def format_bytes(n: int | None) -> str:
    if n is None:
        return "n/a"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(n)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{n}B"


@dataclass
class StageTimer:
    name: str
    started_at: float = field(default_factory=time.perf_counter)
    elapsed_s: float | None = None

    def stop(self) -> float:
        self.elapsed_s = time.perf_counter() - self.started_at
        return self.elapsed_s


@dataclass
class ResourceSnapshot:
    label: str
    rss: int | None
    disk: dict[str, int] | None
    notes: dict[str, Any] = field(default_factory=dict)

    def to_log_line(self) -> str:
        free = self.disk["free"] if self.disk else None
        extras = " ".join(f"{k}={v}" for k, v in self.notes.items())
        return (
            f"[frame_selection:telemetry] {self.label} "
            f"rss={format_bytes(self.rss)} disk_free={format_bytes(free)}"
            + (f" {extras}" if extras else "")
        )


def snapshot(label: str, path: Path | None = None, **notes: Any) -> ResourceSnapshot:
    snap = ResourceSnapshot(
        label=label,
        rss=rss_bytes(),
        disk=disk_usage(path) if path is not None else None,
        notes=notes,
    )
    logger.info(snap.to_log_line())
    return snap


def ensure_disk_space(path: Path, required_bytes: int, on_log=None) -> None:
    usage = disk_usage(path)
    if usage is None:
        return
    if usage["free"] < required_bytes:
        msg = (
            f"Insufficient free disk space under {path}: "
            f"need ~{format_bytes(required_bytes)}, have {format_bytes(usage['free'])}"
        )
        if on_log:
            on_log(msg)
        raise RuntimeError(msg)
