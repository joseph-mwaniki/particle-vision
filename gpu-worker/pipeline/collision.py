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
