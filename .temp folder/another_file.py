_init_.py

"""Reconstruction pipeline — placeholder implementations."""

from .colmap import run_colmap
from .gsplat_train import train_gsplat
from .collision import generate_collision_mesh
from .convert import convert_to_splat
from .upload import upload_results

__all__ = [
    "run_colmap",
    "train_gsplat",
    "generate_collision_mesh",
    "convert_to_splat",
    "upload_results",
]

collision.py

"""Collision mesh generation stage."""

import logging
import struct
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]


def _read_colmap_points3d_bin(path: Path):
    import numpy as np

    points = []
    with open(path, "rb") as f:
        num_points = struct.unpack("<Q", f.read(8))[0]
        for _ in range(num_points):
            data = f.read(43)
            if len(data) < 43:
                break
            x, y, z = struct.unpack("<ddd", data[:24])
            points.append((x, y, z))
    return np.array(points, dtype=np.float64) if points else np.empty((0, 3))


def _write_minimal_glb(output_path: Path, vertices, faces) -> None:
    """Write a minimal binary GLB with one mesh (no external deps fallback)."""
    import json

    verts = vertices.astype("float32").flatten().tolist()
    idx = faces.astype("uint32").flatten().tolist()

    # Interleaved buffer: positions then indices
    import numpy as np

    vert_bytes = np.array(verts, dtype=np.float32).tobytes()
    idx_bytes = np.array(idx, dtype=np.uint32).tobytes()
    bin_data = vert_bytes + idx_bytes

    gltf = {
        "asset": {"version": "2.0", "generator": "remote-view-gpu-worker"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "mode": 4,
                    }
                ]
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(vertices),
                "type": "VEC3",
                "max": vertices.max(axis=0).tolist(),
                "min": vertices.min(axis=0).tolist(),
            },
            {
                "bufferView": 1,
                "componentType": 5125,
                "count": len(faces) * 3,
                "type": "SCALAR",
            },
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(vert_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": len(vert_bytes), "byteLength": len(idx_bytes), "target": 34963},
        ],
        "buffers": [{"byteLength": len(bin_data)}],
    }

    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_pad = (4 - len(json_bytes) % 4) % 4
    json_bytes += b" " * json_pad
    bin_pad = (4 - len(bin_data) % 4) % 4
    bin_data += b"\x00" * bin_pad

    header = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(json_bytes) + 8 + len(bin_data))
    json_chunk = struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
    bin_chunk = struct.pack("<I4s", len(bin_data), b"BIN\x00") + bin_data

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(header + json_chunk + bin_chunk)


def generate_collision_mesh(
    colmap_dir: Path,
    output_dir: Path,
    on_log: Optional[LogFn] = None,
) -> Path:
    """
    Generate a simplified collision mesh from COLMAP sparse point cloud.

    Uses open3d convex hull when available; falls back to axis-aligned bounding box.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "collision.glb"

    sparse_dir = colmap_dir / "sparse" / "0"
    if not sparse_dir.is_dir():
        sparse_dir = colmap_dir / "sparse"

    points_bin = sparse_dir / "points3D.bin"
    if not points_bin.is_file():
        raise RuntimeError(f"COLMAP points3D.bin not found at {points_bin}")

    if on_log:
        on_log("[collision] Building mesh from sparse point cloud")

    points = _read_colmap_points3d_bin(points_bin)
    if len(points) < 4:
        raise RuntimeError("Not enough COLMAP points to build collision mesh")

    import numpy as np

    try:
        import open3d as o3d

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd = pcd.voxel_down_sample(voxel_size=max(np.ptp(points, axis=0) / 100.0, 0.01))
        hull, _ = pcd.compute_convex_hull()
        vertices = np.asarray(hull.vertices)
        faces = np.asarray(hull.triangles)

        try:
            import trimesh

            mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            mesh.export(str(output_path))
            if on_log:
                on_log(f"[collision] Exported convex hull GLB ({len(faces)} faces)")
            return output_path
        except ImportError:
            _write_minimal_glb(output_path, vertices, faces)
            if on_log:
                on_log(f"[collision] Exported convex hull GLB ({len(faces)} faces, minimal writer)")
            return output_path

    except ImportError:
        if on_log:
            on_log("[collision] open3d not installed — using bounding box fallback")

    # Bounding box fallback (12 triangles, 8 vertices)
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    x0, y0, z0 = mins
    x1, y1, z1 = maxs
    vertices = np.array(
        [
            [x0, y0, z0],
            [x1, y0, z0],
            [x1, y1, z0],
            [x0, y1, z0],
            [x0, y0, z1],
            [x1, y0, z1],
            [x1, y1, z1],
            [x0, y1, z1],
        ],
        dtype=np.float32,
    )
    faces = np.array(
        [
            [0, 1, 2],
            [0, 2, 3],
            [4, 6, 5],
            [4, 7, 6],
            [0, 4, 5],
            [0, 5, 1],
            [1, 5, 6],
            [1, 6, 2],
            [2, 6, 7],
            [2, 7, 3],
            [3, 7, 4],
            [3, 4, 0],
        ],
        dtype=np.uint32,
    )
    _write_minimal_glb(output_path, vertices, faces)
    if on_log:
        on_log("[collision] Exported bounding-box collision GLB")
    return output_path


colmap.py

"""COLMAP reconstruction stage."""

import logging
import os
import shutil
from pathlib import Path
from typing import Callable, Optional

from config import COLMAP_QUALITY, COLMAP_USE_GPU, find_colmap_binary
from .utils import ensure_dir, extract_images_zip, run_command

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]
ProgressFn = Callable[[str, int, str], None]

# COLMAP quality presets (camera model + feature settings)
_QUALITY_PRESETS = {
    "low": {"max_image_size": 1600, "max_num_features": 4096},
    "medium": {"max_image_size": 2048, "max_num_features": 8192},
    "high": {"max_image_size": 3200, "max_num_features": 16384},
}


def _colmap_quality() -> dict:
    return _QUALITY_PRESETS.get(COLMAP_QUALITY, _QUALITY_PRESETS["medium"])


def _wrap_xvfb_if_needed(cmd: list[str]) -> list[str]:
    """Wrap command with xvfb-run if in headless environment and xvfb-run is available."""
    if COLMAP_USE_GPU == "1" and "DISPLAY" not in os.environ:
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            return [xvfb, "-a", *cmd]
    return cmd


def run_colmap(
    images_dir: Path,
    output_dir: Path,
    zip_path: Optional[Path] = None,
    on_log: Optional[LogFn] = None,
    on_progress: Optional[ProgressFn] = None,
) -> Path:
    """
    Run COLMAP structure-from-motion on uploaded images.

        Pipeline:
            images/ → feature_extractor → exhaustive_matcher → mapper → sparse/0/

    Returns path to COLMAP dataset root (contains images/ + sparse/0/).
    """
    colmap_bin = find_colmap_binary()
    if not colmap_bin:
        raise RuntimeError("COLMAP binary not found. Install COLMAP and ensure it is on PATH.")

    work_dir = ensure_dir(output_dir)
    database_path = work_dir / "database.db"
    sparse_dir = ensure_dir(work_dir / "sparse")

    if zip_path and zip_path.is_file():
        source_images = extract_images_zip(zip_path, work_dir, on_log=on_log)
    else:
        source_images = Path(images_dir)
        if not source_images.is_dir():
            raise RuntimeError(f"Images directory not found: {source_images}")

    # gsplat Parser expects data_dir/images and data_dir/sparse/0.
    # Copy only image files so COLMAP never sees manifests, videos, or rejected frames.
    dataset_images = ensure_dir(work_dir / "images")
    if source_images.resolve() != dataset_images.resolve():
        if dataset_images.exists():
            shutil.rmtree(dataset_images)
        dataset_images.mkdir(parents=True, exist_ok=True)
        image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
        copied = 0
        for path in sorted(source_images.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in image_extensions:
                continue
            destination = dataset_images / path.name
            if destination.exists():
                destination = dataset_images / f"{path.stem}_{copied:06d}{path.suffix.lower()}"
            shutil.copy2(path, destination)
            copied += 1
        if copied == 0:
            raise RuntimeError(f"No selected images found for COLMAP in {source_images}")
        if on_log:
            on_log(f"Copied {copied} selected frames into COLMAP image directory")

    preset = _colmap_quality()

    def report(substage: str, progress: int, message: str) -> None:
        logger.info("[COLMAP:%s] %s", substage, message)
        if on_log:
            on_log(f"[COLMAP:{substage}] {message}")
        if on_progress:
            on_progress(substage, progress, message)

    report("extract_features", 12, f"Running feature extraction (GPU={COLMAP_USE_GPU})")
    try:
        run_command(
            _wrap_xvfb_if_needed([
                colmap_bin,
                "feature_extractor",
                "--database_path",
                str(database_path),
                "--image_path",
                str(dataset_images),
                "--ImageReader.single_camera",
                "1",
                "--FeatureExtraction.max_image_size",
                str(preset["max_image_size"]),
                "--SiftExtraction.max_num_features",
                str(preset["max_num_features"]),
                "--FeatureExtraction.use_gpu",
                str(COLMAP_USE_GPU),
            ]),
            on_log=on_log,
        )
    except Exception as exc:
        if COLMAP_USE_GPU == "1":
            logger.warning("GPU feature extraction failed (%s). Falling back to CPU extraction.", exc)
            if on_log:
                on_log(f"Warning: GPU extraction failed ({exc}). Retrying on CPU...")
            run_command(
                [
                    colmap_bin,
                    "feature_extractor",
                    "--database_path",
                    str(database_path),
                    "--image_path",
                    str(dataset_images),
                    "--ImageReader.single_camera",
                    "1",
                    "--FeatureExtraction.max_image_size",
                    str(preset["max_image_size"]),
                    "--SiftExtraction.max_num_features",
                    str(preset["max_num_features"]),
                    "--FeatureExtraction.use_gpu",
                    "0",
                ],
                on_log=on_log,
            )
        else:
            raise

    report("match_features", 20, f"Running exhaustive feature matching (GPU={COLMAP_USE_GPU})")
    try:
        run_command(
            _wrap_xvfb_if_needed([
                colmap_bin,
                "exhaustive_matcher",
                "--database_path",
                str(database_path),
                "--FeatureMatching.use_gpu",
                str(COLMAP_USE_GPU),
            ]),
            on_log=on_log,
        )
    except Exception as exc:
        if COLMAP_USE_GPU == "1":
            logger.warning("GPU feature matching failed (%s). Falling back to CPU matching.", exc)
            if on_log:
                on_log(f"Warning: GPU matching failed ({exc}). Retrying on CPU...")
            run_command(
                [
                    colmap_bin,
                    "exhaustive_matcher",
                    "--database_path",
                    str(database_path),
                    "--FeatureMatching.use_gpu",
                    "0",
                ],
                on_log=on_log,
            )
        else:
            raise

    report("sparse_reconstruction", 28, "Running GLOMAP global mapper (SfM)")
    run_command(
        [
            colmap_bin,
            "global_mapper",
            "--database_path",
            str(database_path),
            "--image_path",
            str(dataset_images),
            "--output_path",
            str(sparse_dir),
            "--GlobalMapper.multiple_models",
            "0",
        ],
        on_log=on_log,
    )

    sparse_model = sparse_dir / "0"
    if not sparse_model.is_dir():
        # Some COLMAP versions write directly to sparse/
        if (sparse_dir / "cameras.bin").exists() or (sparse_dir / "cameras.txt").exists():
            sparse_model = sparse_dir
        else:
            raise RuntimeError("COLMAP mapper did not produce sparse/0 reconstruction")

    report("undistort", 30, f"Sparse reconstruction ready at {sparse_model}")
    return work_dir

convert.py

"""Splat format conversion stage."""

import logging
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]


def _export_from_checkpoint(ckpt_path: Path, output_path: Path, on_log: Optional[LogFn] = None) -> Path:
    import torch
    from gsplat import export_splats

    if on_log:
        on_log(f"Loading checkpoint {ckpt_path.name}")

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=True)
    splats = ckpt["splats"]

    sh0 = splats["sh0"]
    shN = splats.get("shN")
    if shN is None:
        import torch as th
        shN = th.empty([sh0.shape[0], 0, 3], device=sh0.device, dtype=sh0.dtype)

    export_splats(
        means=splats["means"],
        scales=splats["scales"],
        quats=splats["quats"],
        opacities=splats["opacities"],
        sh0=sh0,
        shN=shN,
        format="splat",
        save_to=str(output_path),
    )
    return output_path


def _export_from_ply(ply_path: Path, output_path: Path, on_log: Optional[LogFn] = None) -> Path:
    """Convert Gaussian PLY to .splat using gsplat exporter after loading vertices."""
    import numpy as np
    import torch
    from gsplat import export_splats

    if on_log:
        on_log(f"Parsing PLY {ply_path.name}")

    # Minimal PLY reader for 3DGS vertex format
    with open(ply_path, "rb") as f:
        header_lines = []
        while True:
            line = f.readline().decode("ascii", errors="ignore").strip()
            header_lines.append(line)
            if line == "end_header":
                break
        body = f.read()

    vertex_count = 0
    properties: list[str] = []
    for line in header_lines:
        if line.startswith("element vertex"):
            vertex_count = int(line.split()[-1])
        elif line.startswith("property float"):
            properties.append(line.split()[-1])

    if vertex_count == 0:
        raise RuntimeError(f"Could not parse PLY header from {ply_path}")

    dtype = np.dtype([(p, "<f4") for p in properties])
    vertices = np.frombuffer(body, dtype=dtype, count=vertex_count)

    def col(name: str) -> torch.Tensor:
        if name not in vertices.dtype.names:
            raise RuntimeError(f"PLY missing property: {name}")
        return torch.from_numpy(vertices[name].copy())

    # Standard 3DGS PLY field names
    means = torch.stack([col("x"), col("y"), col("z")], dim=-1)
    scales = torch.stack([col("scale_0"), col("scale_1"), col("scale_2")], dim=-1)
    quats = torch.stack([col("rot_0"), col("rot_1"), col("rot_2"), col("rot_3")], dim=-1)
    opacities = col("opacity")
    sh0 = torch.stack([col("f_dc_0"), col("f_dc_1"), col("f_dc_2")], dim=-1).unsqueeze(1)

    shN_cols = [n for n in vertices.dtype.names if n.startswith("f_rest_")]
    if shN_cols:
        shN_vals = torch.stack([col(n) for n in sorted(shN_cols)], dim=-1)
        k = shN_vals.shape[1] // 3
        shN = shN_vals.reshape(shN_vals.shape[0], k, 3)
    else:
        shN = torch.empty([means.shape[0], 0, 3])

    export_splats(
        means=means,
        scales=scales,
        quats=quats,
        opacities=opacities,
        sh0=sh0,
        shN=shN,
        format="splat",
        save_to=str(output_path),
    )
    return output_path


def convert_to_splat(model_path: Path, output_dir: Path, on_log: Optional[LogFn] = None) -> Path:
    """
    Convert trained Gaussian model (PLY or checkpoint) to web-ready .splat format.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "scene.splat"

    logger.info("[convert] model=%s → %s", model_path, output_path)
    if on_log:
        on_log(f"[export] Converting {model_path.name} → scene.splat")

    if not model_path.is_file():
        raise RuntimeError(f"Model file not found: {model_path}")

    suffix = model_path.suffix.lower()
    if suffix == ".pt":
        return _export_from_checkpoint(model_path, output_path, on_log=on_log)
    if suffix == ".ply":
        return _export_from_ply(model_path, output_path, on_log=on_log)

    raise RuntimeError(f"Unsupported model format: {model_path}")

gsplat_train.py

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

    # Vast.ai injects the system CUDA library path. PyTorch ships
    # its own compatible CUDA/cuBLAS libraries, so don't override
    # PyTorch's library resolution for the gsplat subprocess.
    env.pop("LD_LIBRARY_PATH", None)

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

upload.py

"""Upload generated assets directly from temporary worker storage to R2."""

import logging
from pathlib import Path

from typing import Callable, Optional

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]


def upload_results(
    splat_path: Path,
    collision_path: Path,
    output_uploads: dict[str, dict[str, str]],
    on_log: Optional[LogFn] = None,
) -> dict:
    if not splat_path.is_file():
        raise RuntimeError(f"scene.splat not found at {splat_path}")
    if not collision_path.is_file():
        raise RuntimeError(f"collision.glb not found at {collision_path}")
    import requests

    for asset, file_path, content_type in (
        ("splat", splat_path, "application/octet-stream"),
        ("collision", collision_path, "model/gltf-binary"),
    ):
        destination = output_uploads[asset]
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if on_log:
            on_log(f"[upload] Sending {file_path.name} directly to object storage ({size_mb:.1f} MB)")
        with file_path.open("rb") as body:
            response = requests.put(
                destination["url"],
                data=body,
                headers={"Content-Type": content_type},
                timeout=(10, 300),
            )
        response.raise_for_status()
        logger.info("[upload] Uploaded %s to object key %s", asset, destination["key"])

    if on_log:
        on_log("[upload] Generated assets uploaded directly to object storage")
    return {
        "splat_key": output_uploads["splat"]["key"],
        "collision_key": output_uploads["collision"]["key"],
    }

utils.py

"""Shared pipeline utilities."""

import json
import logging
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable, Optional

from .frame_selection import SelectorConfig, select_frames

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_images_zip(zip_path: Path, dest_dir: Path, on_log: Optional[LogFn] = None) -> Path:
    """Extract one uploaded ZIP to dest_dir/images/."""
    return extract_images_zips([zip_path], dest_dir, on_log=on_log)


def extract_images_zips(zip_paths: list[Path], dest_dir: Path, on_log: Optional[LogFn] = None) -> Path:
    """Extract image files from source archives into isolated temporary folders."""
    images_dir = ensure_dir(dest_dir / "images")
    image_extensions = IMAGE_EXTENSIONS
    image_count = 0
    for index, zip_path in enumerate(zip_paths, start=1):
        namespace = re.sub(r"[^a-zA-Z0-9_-]+", "-", zip_path.stem).strip("-")[:80]
        source_dir = images_dir / f"{index:03d}-{namespace or 'source'}"
        if on_log:
            on_log(f"Extracting {zip_path.name} to {source_dir}")
        with zipfile.ZipFile(zip_path, "r") as archive:
            for entry in archive.infolist():
                normalized = entry.filename.replace("\\", "/")
                entry_path = PurePosixPath(normalized)
                if entry.is_dir() or entry_path.is_absolute() or ".." in entry_path.parts:
                    continue
                if entry_path.suffix.lower() not in image_extensions:
                    continue
                destination = source_dir.joinpath(*entry_path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry, "r") as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                image_count += 1

    if image_count == 0:
        raise RuntimeError("No images found after extracting the uploaded ZIP files")
    if on_log:
        on_log(f"Extracted {image_count} images from {len(zip_paths)} ZIP file(s)")
    return images_dir


def _clear_dir(path: Path) -> None:
    if not path.exists():
        return
    for item in sorted(path.iterdir(), reverse=True):
        if item.is_file() or item.is_symlink():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)


def extract_frames_from_video(
    video_path: Path,
    dest_dir: Path,
    on_log: Optional[LogFn] = None,
    job_id: Optional[str] = None,
    config: Optional[SelectorConfig] = None,
) -> Path:
    """Run CPU frame selection and return the COLMAP-ready selected-images directory.

    Only frames accepted by the selection algorithm are written for COLMAP. The
    source video is not sampled at a fixed FPS and is never passed through as
    an unfiltered image sequence.
    """
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise RuntimeError(f"Source video is missing or empty: {video_path}")

    output_root = ensure_dir(dest_dir / "frame_selection")
    colmap_images = output_root / "colmap_input" / "images"
    _clear_dir(output_root)

    selector_config = config or SelectorConfig(max_rejected_preview=0)

    def progress_callback(progress: int, message: str, updates: dict[str, Any] | None = None) -> None:
        if on_log:
            extra = ""
            stats = (updates or {}).get("stats") if updates else None
            if isinstance(stats, dict) and stats.get("selected_frames") is not None:
                extra = f" (selected={stats['selected_frames']})"
            on_log(f"[frame_selection:{progress}%] {message}{extra}")

    if on_log:
        on_log(f"Selecting reconstruction frames from {video_path.name} on CPU")

    try:
        result = select_frames(
            video_path,
            config=selector_config,
            job_id=job_id,
            progress_callback=progress_callback,
            output_root=output_root,
        )
    except ValueError as exc:
        raise RuntimeError(f"Video decoding failed: {exc}") from exc

    selected_count = int(result.get("selected_count") or 0)
    frame_files = sorted(p for p in colmap_images.glob("*.jpg") if p.is_file())
    if selected_count <= 0 or not frame_files:
        raise RuntimeError("Frame selection produced no usable frames for reconstruction")

    for warning in result.get("warnings") or []:
        if on_log:
            on_log(f"[frame_selection] {warning}")

    metadata = {
        "source_video": video_path.name,
        "job_id": result.get("job_id"),
        "frame_count": selected_count,
        "stats": result.get("stats", {}),
        "warnings": result.get("warnings", []),
        "ordered_frames": [p.name for p in frame_files],
        "algorithm": "frame-extractor-algorithm",
    }
    (output_root / "frame_selection.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if on_log:
        on_log(
            f"Frame selection kept {selected_count} of {result.get('stats', {}).get('total_frames', '?')} frames"
        )
    return colmap_images


def run_command(
    cmd: list[str],
    cwd: Optional[Path] = None,
    on_log: Optional[LogFn] = None,
    timeout: Optional[int] = None,
) -> None:
    """Run a subprocess and stream output to logs."""
    cmd_str = " ".join(cmd)
    logger.info("Running: %s", cmd_str)
    if on_log:
        on_log(f"$ {cmd_str}")

    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout and on_log:
        for line in stdout.splitlines()[-20:]:
            on_log(line)
    if result.returncode != 0:
        tail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"Command failed ({result.returncode}): {cmd_str}\n{tail[-2000:]}")


def download_file(url: str, dest_path: Path, on_log: Optional[LogFn] = None) -> Path:
    """Download a file from an HTTP/HTTPS URL to dest_path."""
    import urllib.parse
    import urllib.request

    ensure_dir(dest_path.parent)

    # Encode spaces and special characters in URL path safely
    parsed = urllib.parse.urlsplit(url)
    encoded_path = urllib.parse.quote(urllib.parse.unquote(parsed.path))
    safe_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, encoded_path, parsed.query, parsed.fragment))

    if on_log:
        on_log(f"Downloading source video from object storage...")
    logger.info("Downloading file from %s to %s", safe_url, dest_path)

    urllib.request.urlretrieve(safe_url, str(dest_path))
    if not dest_path.is_file() or dest_path.stat().st_size == 0:
        raise RuntimeError(f"Failed to download or empty file from {safe_url}")
    return dest_path


def find_latest_file(directory: Path, pattern: str) -> Optional[Path]:
    matches = sorted(directory.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None

