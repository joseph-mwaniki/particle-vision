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
