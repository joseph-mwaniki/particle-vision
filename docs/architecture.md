# Architecture

## Overview

Remote View is a monorepo with three independent services connected through documented HTTP interfaces.

```
┌─────────────┐     REST API      ┌─────────────┐    HTTP + callback    ┌─────────────┐
│   Frontend  │ ◄──────────────► │   Backend   │ ◄──────────────────► │ GPU Worker  │
│  (gsplat.js)│                   │  (Express)  │                       │  (Python)   │
└─────────────┘                   └─────────────┘                       └─────────────┘
      │                                  │                                     │
      │ loads scene.splat                │ stores jobs.json                    │ placeholder
      │ loads collision.glb (future)     │ serves /uploads/*                   │ pipeline
      ▼                                  ▼                                     ▼
  WebGL Viewer                      Local filesystem                      /workspace/data
```

## Components

### Frontend (`frontend/`)

- **Stack:** Vite 7, TypeScript 5.8, gsplat.js 1.2.9
- **Role:** Upload images, monitor jobs, view 3D splats
- **Viewer:** `SplatViewer` class wraps gsplat.js Scene/Camera/Renderer
- **Assets:** `scene.splat` (visible), `collision.glb` (invisible, future)

### Backend (`backend/`)

- **Stack:** Express 4, TypeScript 5.4, Node 20+
- **Role:** Job CRUD, file upload, worker dispatch, callback handling
- **Storage:** JSON file (`jobs.json`) + disk uploads (`uploads/`)
- **No:** Database, auth, payments, queues

### GPU Worker (`gpu-worker/`)

- **Stack:** Python 3.10, stdlib HTTP server (placeholder)
- **Role:** Accept training jobs, run pipeline, callback progress
- **Future stack:** PyTorch 2.10 + CUDA 12.8 + gsplat 1.5.3 + COLMAP
- **Deployment:** Docker container, RunPod serverless handler

### Vendored Libraries

| Library | Path | Version | Purpose |
|---------|------|---------|---------|
| gsplat | `gsplat/` | 1.5.3 | CUDA Gaussian Splatting training |
| gsplat.js | `gsplat.js/` | 1.2.9 | WebGL browser viewer |

## Data Flow

### Upload → Train → View

1. User uploads ZIP via frontend `POST /upload`
2. Backend creates job (`status: PENDING`), stores ZIP in `uploads/`
3. User clicks "Start Training" → frontend `POST /train`
4. Backend dispatches `POST {GPU_WORKER_URL}/run`
5. Worker runs placeholder pipeline, sends callbacks to `/internal/worker/callback`
6. Backend updates job status/progress in `jobs.json`
7. Frontend polls `GET /job/:id` every 2 seconds
8. On `COMPLETED`, frontend loads `scene.splat` via gsplat.js `Loader.LoadAsync()`

### Collision Mesh (future)

When implemented, the worker will produce `collision.glb` alongside `scene.splat`. The frontend will load it invisibly for raycasting and physics — not for visual rendering.

## Pipeline Interface

All pipeline functions live in `gpu-worker/pipeline/`:

| Function | Input | Output | Status |
|----------|-------|--------|--------|
| `run_colmap()` | images dir | sparse reconstruction | Placeholder |
| `train_gsplat()` | COLMAP sparse | trained PLY | Placeholder |
| `generate_collision_mesh()` | dense mesh | collision.glb | Placeholder |
| `convert_to_splat()` | PLY | scene.splat | Placeholder |
| `upload_results()` | assets | callback payload | Placeholder |

## Job Status Machine

```
PENDING
  └─► QUEUED
        └─► PROCESSING_COLMAP
              └─► PROCESSING_GSPLAT
                    └─► PROCESSING_COLLISION
                          └─► PROCESSING_EXPORT
                                └─► COMPLETED
                                └─► FAILED (from any state)
```

## Independence

Each service can be developed, built, and deployed independently:

- Frontend builds to static files (Vite)
- Backend builds to Node.js (`tsc`)
- GPU Worker builds to Docker image

Shared contracts are documented in [api-contract.md](api-contract.md).
