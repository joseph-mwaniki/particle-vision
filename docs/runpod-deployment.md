# RunPod Deployment

This document describes the planned deployment process. The integration layer is ready; GPU training is not yet implemented.

## Architecture on RunPod

```
┌──────────┐     HTTPS      ┌──────────────┐    RunPod API    ┌─────────────────┐
│ Frontend │ ◄────────────► │   Backend    │ ◄──────────────► │  GPU Worker     │
│ (static) │                │ (your server)│                  │ (serverless pod) │
└──────────┘                └──────────────┘                  └─────────────────┘
```

## GPU Worker Deployment

### 1. Build Docker Image

```bash
cd gpu-worker
docker build -t your-registry/remote-view-worker:latest .
docker push your-registry/remote-view-worker:latest
```

### 2. Create RunPod Serverless Endpoint

1. Go to RunPod Console → Serverless → New Endpoint
2. Select your Docker image
3. Configure GPU: RTX 4090 or A100 (recommended for gsplat training)
4. Set handler: `handler.runpod_handler`
5. Set environment variables:

| Variable | Value |
|----------|-------|
| `BACKEND_CALLBACK_URL` | `https://your-api.com/internal/worker/callback` |
| `WORK_DIR` | `/workspace/data` |
| `GSPLAT_STEPS` | `7000` |

### 3. Future CUDA Image

When training is implemented, switch to a CUDA base image:

```dockerfile
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y \
    python3.10 python3-pip colmap

RUN pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
RUN pip install gsplat --index-url https://docs.gsplat.studio/whl/pt210cu128
RUN pip install -r requirements.txt
```

Verified versions: see [dependencies.md](dependencies.md).

## Backend Configuration

```env
PORT=3001
GPU_WORKER_URL=https://api.runpod.ai/v2/{endpoint_id}/run
BACKEND_PUBLIC_URL=https://your-api.com
USE_MOCK_WORKER=false
```

The backend dispatches jobs via `POST {GPU_WORKER_URL}/run` with:

```json
{
  "job_id": "job_abc123",
  "images_path": "/uploads/photos.zip",
  "callback_url": "https://your-api.com/internal/worker/callback"
}
```

## Frontend Deployment

Build static files and deploy to any static host:

```bash
cd frontend
VITE_API_BASE=https://your-api.com npm run build
# Deploy dist/ to Netlify, Vercel, S3, etc.
```

## RunPod Handler Contract

`handler.py` implements the standard RunPod pattern:

```python
def runpod_handler(event: dict) -> dict:
    """
    event = {
        "job_id": str,
        "images_path": str,
        "callback_url": str
    }
    returns {"job_id": str, "status": "accepted"}
    """
```

The handler starts pipeline processing in a background thread and returns immediately. Progress is reported via HTTP callbacks to the backend.

## Deployment Checklist

- [ ] Build and push GPU worker Docker image
- [ ] Create RunPod serverless endpoint with GPU
- [ ] Deploy backend with `USE_MOCK_WORKER=false`
- [ ] Set `BACKEND_PUBLIC_URL` to publicly accessible URL
- [ ] Deploy frontend with `VITE_API_BASE` pointing to backend
- [ ] Test upload → train → callback → view flow
- [ ] Implement real pipeline functions (currently placeholders)
- [ ] Switch Docker image to CUDA base with gsplat deps
- [ ] Configure persistent storage for uploads/outputs

## Storage Considerations

Current implementation uses local disk (`backend/uploads/`). For production:

- Use S3/object storage for uploaded ZIPs and output assets
- Worker needs access to input images (shared volume or pre-signed URLs)
- Output `scene.splat` and `collision.glb` should be uploaded to object storage

These are future enhancements — not part of the integration layer.

## Estimated GPU Requirements (Future)

Based on gsplat documentation:

| Metric | Value |
|--------|-------|
| VRAM | 8–24 GB depending on scene size |
| Training time | ~15–30 min for 7000 steps |
| Recommended GPU | RTX 4090, A100 |

From gsplat README: training takes up to 4x less GPU memory than official implementation.
