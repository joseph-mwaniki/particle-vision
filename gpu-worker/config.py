"""GPU worker configuration."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Ensure Qt uses offscreen platform for headless environments like COLMAP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Pipeline mode
USE_MOCK = os.getenv("USE_MOCK", "false").lower() in ("1", "true", "yes")

# Paths
WORK_DIR = Path(os.getenv("WORK_DIR", "/workspace/data"))
UPLOAD_DIR = WORK_DIR / "uploads"
OUTPUT_DIR = WORK_DIR / "output"
BACKEND_UPLOADS_DIR = Path(os.getenv("BACKEND_UPLOADS_DIR", str(WORK_DIR / "uploads")))

# Backend callback
BACKEND_CALLBACK_URL = os.getenv(
    "BACKEND_CALLBACK_URL", "https://particle-vision-backend.onrender.com"
)

# Training defaults
GSPLAT_STEPS = int(os.getenv("GSPLAT_STEPS", "7000"))
COLMAP_QUALITY = os.getenv("COLMAP_QUALITY", "medium")
COLMAP_BINARY = os.getenv("COLMAP_BINARY", "colmap")
COLMAP_USE_GPU = os.getenv("COLMAP_USE_GPU", "1")
COLMAP_MATCHER = os.getenv("COLMAP_MATCHER", "exhaustive")

# gsplat source path (vendored in monorepo, mounted in Docker)
GSPLAT_REPO_PATH = Path(os.getenv("GSPLAT_REPO_PATH", str(Path(__file__).resolve().parent.parent / "gsplat")))

# Pipeline stage identifiers (match backend JobStatus values)
STAGE_QUEUED = "QUEUED"
STAGE_COLMAP = "PROCESSING_COLMAP"
STAGE_GSPLAT = "PROCESSING_GSPLAT"
STAGE_COLLISION = "PROCESSING_COLLISION"
STAGE_EXPORT = "PROCESSING_EXPORT"
STAGE_COMPLETED = "COMPLETED"
STAGE_FAILED = "FAILED"

# COLMAP sub-stages reported under PROCESSING_COLMAP
COLMAP_SUBSTAGES = (
    "extract_features",
    "match_features",
    "sparse_reconstruction",
    "undistort",
)


def find_colmap_binary() -> Optional[str]:
    """Return path to COLMAP binary if available."""
    configured = shutil.which(COLMAP_BINARY)
    if configured:
        return configured
    return shutil.which("colmap")


def check_colmap_available() -> tuple[bool, str]:
    """Verify COLMAP binary is installed and runnable."""
    binary = find_colmap_binary()
    if not binary:
        return False, f"COLMAP binary '{COLMAP_BINARY}' not found on PATH"
    try:
        result = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0 and not result.stdout and not result.stderr:
            return False, f"COLMAP at {binary} failed to run"
        return True, binary
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"COLMAP check failed: {exc}"


def check_torch_cuda_available() -> tuple[bool, str]:
    """Verify PyTorch with CUDA is available."""
    try:
        import torch
    except ImportError:
        return False, "PyTorch is not installed"

    if not torch.cuda.is_available():
        return False, "PyTorch is installed but CUDA is not available"
    device = torch.cuda.get_device_name(0)
    return True, f"CUDA available ({device})"


def check_gsplat_available() -> tuple[bool, str]:
    """Verify gsplat Python package is importable."""
    try:
        import gsplat  # noqa: F401
        from gsplat import export_splats  # noqa: F401
    except ImportError as exc:
        return False, f"gsplat is not installed: {exc}"

    if not GSPLAT_REPO_PATH.is_dir():
        return False, f"gsplat repo not found at {GSPLAT_REPO_PATH}"
    trainer = GSPLAT_REPO_PATH / "examples" / "simple_trainer.py"
    if not trainer.is_file():
        return False, f"simple_trainer.py not found at {trainer}"
    return True, str(GSPLAT_REPO_PATH)


def validate_pipeline_environment() -> dict[str, tuple[bool, str]]:
    """Run all runtime checks for the real pipeline."""
    return {
        "colmap": check_colmap_available(),
        "torch_cuda": check_torch_cuda_available(),
        "gsplat": check_gsplat_available(),
        "python": (sys.version_info >= (3, 10), f"Python {sys.version_info.major}.{sys.version_info.minor}"),
    }


def require_pipeline_environment() -> None:
    """Raise RuntimeError if the real pipeline cannot run."""
    checks = validate_pipeline_environment()
    failures = [f"{name}: {msg}" for name, (ok, msg) in checks.items() if not ok]
    if failures:
        raise RuntimeError(
            "Pipeline environment check failed:\n  - " + "\n  - ".join(failures)
        )
