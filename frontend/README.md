# Frontend

Vite + TypeScript dashboard with gsplat.js 3D viewer.

## Features

- Upload ZIP files directly to R2 with presigned multipart URLs
- Start training via `POST /train`
- Poll job status via `GET /job/:id`
- Load completed assets from signed or public R2 URLs
- Load local sample `.splat` via "Load Sample" button
- Architecture ready for invisible `collision.glb` loading

## Installation

```bash
# Build gsplat.js library first (optional — frontend uses npm gsplat by default)
# cd ../gsplat.js && npm install && npm run build

# Install frontend
cd ../frontend
npm install
npm run download-sample
npm run dev
```

Open http://localhost:5173

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE` | `/api` | API base URL (proxied to backend in dev) |

## API Integration

API and direct-upload calls are in `src/api.ts`:

```typescript
checkHealth()     // GET  /health
uploadZipFiles()  // Browser → R2 multipart upload, API receives metadata only
startTraining()   // POST /train
getJob(id)        // GET  /job/:id
listJobs()        // GET  /job
```

## Viewer Architecture

`src/viewer/viewer.ts` wraps gsplat.js:

- `loadSplat(url)` — loads `scene.splat` for rendering
- `loadCollisionMesh(url)` — placeholder for invisible `collision.glb` (future physics/navigation)

## Build

```bash
npm run build
npm run preview
```

## Sample Splat

Download the bundled sample:

```bash
npm run download-sample
```

This fetches `bonsai-7k-mini.splat` from HuggingFace into `public/samples/bonsai.splat`.
