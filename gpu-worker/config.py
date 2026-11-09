"""GPU worker configuration."""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Ensure Qt uses offscreen platform for headless environments like COLMAP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Pipeline mode
USE_MOCK = os.getenv("USE_MOCK", "false").lower() in ("1", "true", "yes")

# Paths
WORK_DIR = Path(os.getenv("WORK_DIR", "/workspace/data"))

# Training defaults
GSPLAT_STEPS = int(os.getenv("GSPLAT_STEPS", "7000"))
COLMAP_QUALITY = os.getenv("COLMAP_QUALITY", "medium")
COLMAP_BINARY = os.getenv("COLMAP_BINARY", "colmap")
COLMAP_USE_GPU = os.getenv("COLMAP_USE_GPU", "1")
COLMAP_MATCHER = os.getenv("COLMAP_MATCHER", "sequential")
# Sequential matcher: compare each frame against this many neighbors on each side
COLMAP_SEQUENTIAL_OVERLAP = int(os.getenv("COLMAP_SEQUENTIAL_OVERLAP", "10"))
COLMAP_SEQUENTIAL_QUADRATIC_OVERLAP = os.getenv("COLMAP_SEQUENTIAL_QUADRATIC_OVERLAP", "1")

# gsplat source path (vendored in monorepo, mounted in Docker)
GSPLAT_REPO_PATH = Path(os.getenv("GSPLAT_REPO_PATH", str(Path(__file__).resolve().parent.parent / "gsplat")))

# Pipeline stage identifiers (match backend JobStatus values)
STAGE_QUEUED = "QUEUED"
STAGE_FRAME_SELECTION = "PROCESSING_FRAME_SELECTION"
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


def check_gsplat_cuda_backend() -> tuple[bool, str]:
    """Verify gsplat's compiled CUDA extension loaded (not CPU fallback)."""
    try:
        from gsplat.cuda._backend import _C, cuda_toolkit_available
    except Exception as exc:
        return False, f"import gsplat.cuda._backend failed: {type(exc).__name__}: {exc}"

    toolkit = cuda_toolkit_available()
    logger.info("gsplat: cuda_toolkit_available=%s _C_is_none=%s", toolkit, _C is None)
    if _C is None:
        return False, f"gsplat CUDA extension not loaded (cuda_toolkit_available={toolkit}); CPU fallback active"

    try:
        import torch
        from gsplat import rasterization

        dev = "cuda"
        rasterization(
            torch.zeros(1, 3, device=dev),
            torch.tensor([[1.0, 0.0, 0.0, 0.0]], device=dev),
            torch.ones(1, 3, device=dev) * 0.1,
            torch.ones(1, device=dev),
            torch.zeros(1, 3, device=dev),
            torch.eye(4, device=dev).unsqueeze(0),
            torch.eye(3, device=dev).unsqueeze(0),
            64,
            64,
        )
        torch.cuda.synchronize()
    except Exception as exc:
        return False, f"gsplat kernel launch failed: {type(exc).__name__}: {exc}"
    return True, "gsplat CUDA kernels functional"


def check_colmap_cuda_backend() -> tuple[bool, str]:
    """Verify COLMAP binary was built with CUDA and can see the GPU."""
    binary = find_colmap_binary()
    if not binary:
        return False, f"COLMAP binary '{COLMAP_BINARY}' not found on PATH"
    try:
        result = subprocess.run(
            [binary, "feature_extractor", "-h"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        blob = (result.stdout or "") + (result.stderr or "")
        has_gpu_opt = "use_gpu" in blob.lower()
        logger.info("COLMAP feature_extractor help contains use_gpu=%s", has_gpu_opt)
    except Exception as exc:
        return False, f"COLMAP help probe failed: {exc}"

    try:
        ldd = subprocess.run(
            ["ldd", binary],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        ldd_blob = (ldd.stdout or "") + (ldd.stderr or "")
        cuda_libs = [
            line.strip()
            for line in ldd_blob.splitlines()
            if any(key in line for key in ("libcudart", "libcublas", "libcurand", "libcudnn"))
        ]
        logger.info("COLMAP CUDA-linked libs: %s", cuda_libs or "none")
    except Exception as exc:
        return False, f"COLMAP ldd probe failed: {exc}"

    if not cuda_libs:
        return False, "COLMAP binary is not linked against CUDA libraries"
    return True, f"COLMAP CUDA-linked ({len(cuda_libs)} libs); use_gpu flag present={has_gpu_opt}"


def check_torch_cuda_ops() -> tuple[bool, str]:
    """Exercise basic CUDA ops on torch and log device details."""
    try:
        import torch
    except ImportError:
        return False, "PyTorch is not installed"

    if not torch.cuda.is_available():
        return False, "torch.cuda.is_available() is False"

    try:
        dev = torch.device("cuda:0")
        a = torch.randn(64, 64, device=dev)
        a @ a.T
        torch.cuda.synchronize()
        name = torch.cuda.get_device_name(0)
        cap = torch.cuda.get_device_capability(0)
        logger.info("torch CUDA device=%s capability=%s", name, cap)
    except Exception as exc:
        return False, f"torch CUDA op failed: {type(exc).__name__}: {exc}"
    return True, f"torch CUDA ops OK on {name} (compute {cap[0]}.{cap[1]})"


def validate_pipeline_environment() -> dict[str, tuple[bool, str]]:
    """Run all runtime checks for the real pipeline."""
    return {
        "colmap": check_colmap_available(),
        "colmap_cuda": check_colmap_cuda_backend(),
        "torch_cuda": check_torch_cuda_available(),
        "torch_cuda_ops": check_torch_cuda_ops(),
        "gsplat": check_gsplat_available(),
        "gsplat_cuda": check_gsplat_cuda_backend(),
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
