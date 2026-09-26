# Architecture

## Overview

Remote View is a monorepo with three independent services connected through documented HTTP interfaces.

```
Browser ──direct multipart PUT──► Cloudflare R2 ◄──signed PUT── GPU Worker
      │                                   ▲                         │
      │ API metadata / signed URLs        │ signed GET              │ temporary WORK_DIR
      ▼                                   │                         ▼
Vercel API ──Postgres metadata──► Neon/Postgres          COLMAP + gsplat
      ▲                                                             │
      └──────────────────── status/key callback ────────────────────┘
Browser ◄──────────── signed/public R2 asset URLs ───────────────┘
```

## Components

### Frontend (`frontend/`)

- **Stack:** Vite 7, TypeScript 5.8, gsplat.js 1.2.9
- **Role:** Upload ZIP parts directly to R2, monitor jobs, view 3D splats directly from R2
- **Viewer:** `SplatViewer` class wraps gsplat.js Scene/Camera/Renderer
- **Assets:** `scene.splat` (visible), `collision.glb` (invisible, future)

### Backend (`backend/`)

- **Stack:** Express 4, TypeScript 5.4, Node 20+
- **Role:** Upload-session metadata, job CRUD, R2 signed URL generation, worker dispatch, callback handling
- **Storage:** Neon/Postgres metadata and R2 object keys; no persistent binary storage
- **No:** Authentication, payments, background queues

### GPU Worker (`gpu-worker/`)

- **Stack:** Python 3.10, HTTP handler, PyTorch/CUDA, gsplat, COLMAP
- **Role:** Download source archives from R2, process in temporary local storage, upload generated assets directly to R2, callback with metadata
- **Deployment:** Docker container, RunPod serverless handler

### Vendored Libraries

| Library | Path | Version | Purpose |
|---------|------|---------|---------|
| gsplat | `gsplat/` | 1.5.3 | CUDA Gaussian Splatting training |
| gsplat.js | `gsplat.js/` | 1.2.9 | WebGL browser viewer |

## Data Flow

### Upload → Train → View

1. Browser requests an upload session and multipart presigned URLs from the API
2. Browser uploads ZIP parts directly to R2; the API stores object-key and completion metadata in Postgres
3. API creates a job linked to the source object keys (`status: PENDING`)
4. User clicks "Start Training" → frontend `POST /train`
5. Backend dispatches signed source GET URLs and output PUT URLs to the GPU worker
6. Worker downloads source ZIPs to temporary `WORK_DIR`, runs the pipeline, uploads generated files directly to R2, then deletes its job directory
7. Worker callbacks report status and R2 keys; backend persists metadata in Postgres
8. Frontend polls job status and loads assets directly from signed or public R2 URLs

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
| `upload_results()` | temporary assets + signed PUT URLs | R2 object keys | Direct worker-to-R2 upload |

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
