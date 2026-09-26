# GPU Worker

RunPod-ready Python worker for 3D Gaussian Splatting reconstruction.

## Status

**Integration layer only.** The pipeline functions exist as placeholders and raise `NotImplementedError` when called. The HTTP handler simulates pipeline progress with callbacks.

## Pipeline Stages

```
R2 source ZIPs → temporary WORK_DIR → run_colmap() → train_gsplat()
     → generate_collision_mesh() → convert_to_splat() → R2 outputs
```

### Collision Mesh (future)

```
Images → COLMAP → Dense Reconstruction → Triangle Mesh
       → Mesh Simplification → Floor Detection → Wall Detection → collision.glb
```

The collision mesh is invisible in the viewer and intended for future physics and navigation.

## Local Development

```bash
python handler.py
# → http://localhost:8080
```

## Docker

```bash
docker build -t remote-view-worker .
docker run -p 8080:8080 \
  remote-view-worker
```

## HTTP Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/run` | Accept training job |

## RunPod Handler

`handler.py` exports `runpod_handler(event)` for serverless deployment:

```python
{
  "job_id": "job_abc123",
  "source_files": [
    { "download_url": "<presigned R2 GET URL>", "original_name": "images.zip" }
  ],
  "output_uploads": {
    "splat": { "key": "splats/job_abc123/scene.splat", "url": "<presigned R2 PUT URL>" },
    "collision": { "key": "splats/job_abc123/collision.glb", "url": "<presigned R2 PUT URL>" }
  },
  "callback_url": "https://api.example.com/internal/worker/callback"
}
```

The worker requires no R2 credentials: the backend sends short-lived signed URLs. ZIPs, extracted images, COLMAP data, and generated outputs live under `WORK_DIR/jobs/{job_id}` only while processing; the worker deletes that directory after success or failure.

## Configuration

See `config.py` and environment variables in [docs/dependencies.md](../docs/dependencies.md).

## Verified Dependencies (for future training)

From `gsplat/.github/workflows/building.yml`:

| Component | Version |
|-----------|---------|
| Python | 3.10 |
| PyTorch | 2.8.0, 2.9.1, 2.10.0 |
| CUDA | 12.6, 12.8, 12.9, 13.0 |
| gsplat | 1.5.3 |
| COLMAP | System install (via apt or build) |

Recommended production combo: **Python 3.10 + PyTorch 2.10.0 + CUDA 12.8 + gsplat 1.5.3**

See [docs/dependencies.md](../docs/dependencies.md) for the full compatibility matrix.
