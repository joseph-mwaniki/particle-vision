# Dependencies

All versions verified from source files in this repository. Do not guess — these are documented from actual project files.

## Runtime Requirements

| Software | Version | Source |
|----------|---------|--------|
| Node.js | >= 20.0.0 | `backend/package.json`, `frontend/package.json` |
| Python | 3.10 | `gsplat/.github/workflows/building.yml` |
| Docker | Latest | `gpu-worker/Dockerfile` |

## Frontend

| Package | Version | Source |
|---------|---------|--------|
| vite | ^7.0.4 | `frontend/package.json` |
| typescript | ^5.8.3 | `frontend/package.json` |
| gsplat (gsplat.js) | 1.2.9 | `gsplat.js/package.json` |

## Backend

| Package | Version | Source |
|---------|---------|--------|
| express | ^4.19.2 | `backend/package.json` |
| typescript | ^5.4.5 | `backend/package.json` |
| multer | ^1.4.5-lts.1 | `backend/package.json` |
| cors | ^2.8.5 | `backend/package.json` |
| dotenv | ^16.4.5 | `backend/package.json` |

## GPU Worker (Placeholder)

The placeholder handler uses Python 3.10 stdlib only. No pip packages required.

## gsplat Training Dependencies (Future)

Verified from `gsplat/.github/workflows/building.yml` and `gsplat/gsplat/version.py`.

### gsplat

| Property | Value | Source |
|----------|-------|--------|
| Version | **1.5.3** | `gsplat/gsplat/version.py` |
| Python | >= 3.7 (3.10 recommended) | `gsplat/setup.py` |
| Build Python | **3.10** | `building.yml` matrix |

### PyTorch + CUDA Compatibility Matrix

From `gsplat/.github/workflows/building.yml` (official CI build matrix):

| PyTorch | CUDA Variants | Notes |
|---------|---------------|-------|
| **2.8.0** | cu126, cu128, cu129 | No cu130 |
| **2.9.1** | cu126, cu128, cu130 | No cu129 |
| **2.10.0** | cu126, cu128, cu130 | No cu129 |

**Recommended for new deployments:** PyTorch 2.10.0 + CUDA 12.8 (cu128)

Install:
```bash
pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
pip install gsplat --index-url https://docs.gsplat.studio/whl/pt210cu128
```

### gsplat Core Dependencies

From `gsplat/setup.py`:

| Package | Notes |
|---------|-------|
| ninja | Build tool |
| numpy | Array operations |
| jaxtyping | Type annotations |
| rich >= 12 | CLI output |
| torch | PyTorch (install separately) |

### gsplat Example Trainer Dependencies

From `gsplat/examples/requirements.txt`:

| Package | Version/Source |
|---------|----------------|
| nvidia-ncore | >= 19.0.0 |
| pycolmap | git: rmbrualla/pycolmap@cc7ea4b |
| viser | latest |
| nerfview | git: nerfstudio-project/nerfview@4538024 |
| numpy | < 2.0.0 |
| scipy | latest |
| scikit-learn | latest |
| torchmetrics[image] | latest |
| opencv-python | latest |
| tyro | >= 0.8.8 |
| fused-ssim | git: rahul-goel/fused-ssim@328dc98 |
| fused-bilagrid | git: harry7557558/fused-bilagrid@49f0ef0 |
| ppisp | git: nv-tlabs/ppisp@v1.0.0 |

Install example deps:
```bash
cd gsplat
pip install -r examples/requirements.txt --no-build-isolation
python -m pip install -e libs/scene -e libs/stage
```

### COLMAP

COLMAP is not a Python package — it must be installed as a system binary.

| Method | Command |
|--------|---------|
| Ubuntu apt | `apt install colmap` (version varies by distro) |
| pycolmap | Bundled COLMAP bindings via `pycolmap` pip package |
| Build from source | https://colmap.github.io/install.html |

The gsplat trainer uses `pycolmap` (pinned commit above) for dataset parsing. For the reconstruction pipeline, COLMAP CLI binaries are needed for `feature_extractor`, `exhaustive_matcher`, and `mapper`.

### CUDA Toolkit

| CUDA Version | Toolkit | gsplat Wheel Tag |
|-------------|---------|------------------|
| 12.6 | CUDA 12.6 | cu126 |
| 12.8 | CUDA 12.8 | cu128 |
| 12.9 | CUDA 12.9 | cu129 |
| 13.0 | CUDA 13.0 | cu130 |

CUDA arch list for builds (from `building.yml`): `7.5;8.0;8.6;9.0`

### Docker Base Images (Future Training)

```dockerfile
# Recommended (devel image required for building CUDA extensions like gsplat from source)
FROM nvidia/cuda:12.8.0-devel-ubuntu22.04

# Alternative versions from CI matrix
FROM nvidia/cuda:12.6.0-devel-ubuntu22.04
FROM nvidia/cuda:13.0.0-devel-ubuntu22.04
```

## gsplat.js

| Property | Value | Source |
|----------|-------|--------|
| Version | 1.2.9 | `gsplat.js/package.json` |
| Build | Vite 5 + WASM workers | `gsplat.js/vite.config.js` |
| WASM | Emscripten compiled sort/data workers | `gsplat.js/wasm/` |

Build:
```bash
cd gsplat.js
npm install
npm run build   # builds WASM + JS bundle to dist/
```

## Environment Variables

See per-project READMEs and [local-development.md](local-development.md).
