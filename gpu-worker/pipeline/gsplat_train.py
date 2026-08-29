"""gsplat training stage — invokes vendored simple_trainer."""

import logging
import os
import sys
from pathlib import Path
from typing import Callable, Optional

from config import GSPLAT_REPO_PATH, GSPLAT_STEPS
from .utils import ensure_dir, find_latest_file, run_command

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]
ProgressFn = Callable[[str, int, str], None]


def train_gsplat(
    colmap_dir: Path,
    output_dir: Path,
    steps: int = GSPLAT_STEPS,
    on_log: Optional[LogFn] = None,
    on_progress: Optional[ProgressFn] = None,
) -> Path:
    """
    Train 3D Gaussian Splatting from COLMAP output using gsplat/examples/simple_trainer.py.

    Returns path to the latest exported PLY checkpoint.
    """
    if not GSPLAT_REPO_PATH.is_dir():
        raise RuntimeError(f"gsplat repo not found at {GSPLAT_REPO_PATH}")

    result_dir = ensure_dir(output_dir)
    examples_dir = GSPLAT_REPO_PATH / "examples"

    def report(substage: str, progress: int, message: str) -> None:
        logger.info("[gsplat:%s] %s", substage, message)
        if on_log:
            on_log(f"[gsplat:{substage}] {message}")
        if on_progress:
            on_progress(substage, progress, message)

    report("init", 35, f"Starting gsplat training ({steps} steps)")
    report("init", 38, f"COLMAP data: {colmap_dir}")

    env = os.environ.copy()
    pythonpath_parts = [str(GSPLAT_REPO_PATH), str(examples_dir)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    cmd = [
        sys.executable,
        "-m",
        "examples.simple_trainer",
        "default",
        "--data-dir",
        str(colmap_dir),
        "--result-dir",
        str(result_dir),
        "--max-steps",
        str(steps),
        "--save-steps",
        str(steps),
        "--eval-steps",
        str(steps),
        "--ply-steps",
        str(steps),
        "--disable-viewer",
        "--disable-video",
        "--save-ply",
        "--data-factor",
        "1",
    ]

    report("train", 45, "Running simple_trainer (this may take a while)")
    result = __import__("subprocess").run(
        cmd,
        cwd=str(GSPLAT_REPO_PATH),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if on_log:
        for line in (stdout + "\n" + stderr).splitlines()[-30:]:
            if line.strip():
                on_log(line)

    if result.returncode != 0:
        tail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"gsplat training failed:\n{tail[-3000:]}")

    ply_dir = result_dir / "ply"
    ply_path = find_latest_file(ply_dir, "point_cloud_*.ply") if ply_dir.is_dir() else None
    if ply_path is None:
        ply_path = find_latest_file(result_dir, "*.ply")

    if ply_path is None:
        ckpt_path = find_latest_file(result_dir / "ckpts", "ckpt_*_rank0.pt")
        if ckpt_path:
            report("export", 65, f"Training complete, checkpoint at {ckpt_path}")
            return ckpt_path
        raise RuntimeError("gsplat training finished but no PLY or checkpoint was produced")

    report("export", 65, f"Training complete, PLY at {ply_path}")
    return ply_path
