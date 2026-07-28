# Python Dependencies for GPU Worker & gsplat Pipeline

## Overview
This document provides step‑by‑step instructions to set up the required Python environment for the **GPU worker** and the **gsplat** reconstruction pipeline.

## 1. Prerequisites
- **Operating System**: Linux (tested on Ubuntu 22.04).
- **CUDA**: Ensure the CUDA toolkit matching your GPU driver is installed (e.g., `cuda-12-1`). Verify with `nvcc --version`.
- **Python**: Python 3.10 or newer. Use `python3 --version` to confirm.
- **Node.js**: Already required for the frontend; keep it installed.

## 2. Create an Isolated Environment
```bash
# Navigate to the project root
cd "$(pwd)"
# Create a virtual environment inside the repo
python3 -m venv .venv
# Activate it
source .venv/bin/activate
```
> **Tip**: Activate the environment each time you work on the pipeline.

## 3. Install Core Packages
```bash
# Upgrade pip and setuptools
pip install --upgrade pip setuptools wheel

# Install required libraries
pip install \
    torch==2.3.0+cu121 -f https://download.pytorch.org/whl/torch_stable.html \
    torchvision==0.18.0+cu121 -f https://download.pytorch.org/whl/torch_stable.html \
    tqdm numpy scipy matplotlib
```
- The `torch` wheels above target CUDA 12.1; adjust `cuXXX` to match your installed toolkit.

## 4. Install **gsplat** (Python side)
The GPU worker relies on the `gsplat` Python package that provides CUDA kernels for Gaussian splatting.
```bash
pip install gsplat==0.1.7
```
> If you need a newer version, check the [gsplat PyPI page](https://pypi.org/project/gsplat/).

For the vendored gsplat 1.5.3 in this repo, see `docs/dependencies.md` for the verified PyTorch/CUDA matrix.

## 5. Install **COLMAP** (Structure‑from‑Motion)
COLMAP is an external binary, not a pip package.
```bash
# Ubuntu/Debian example using apt (may provide an older version)
sudo apt-get update && sudo apt-get install -y colmap
```
- **Alternative (recommended)**: Build from source for the latest features.
  ```bash
  git clone https://github.com/colmap/colmap.git
  cd colmap
  mkdir build && cd build
  cmake .. -DCMAKE_BUILD_TYPE=Release
  make -j$(nproc)
  sudo make install
  ```
- Verify installation with `colmap --version`.

## 6. Verify the Environment
```bash
python - <<'PY'
import torch, gsplat, subprocess, sys
print('Torch version:', torch.__version__)
print('CUDA available:', torch.cuda.is_available())
print('gsplat version:', gsplat.__version__)
# Check COLMAP binary
subprocess.run(['colmap', '--help'], check=True)
PY
```
If all commands print without errors, the environment is ready.

## 7. Optional: Export Paths (for non‑standard installs)
```bash
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:$LD_LIBRARY_PATH"
```
Add the above lines to `~/.bashrc` if you installed CUDA in a custom location.

## 8. Run the Real Pipeline
```bash
export USE_MOCK=false
export GSPLAT_REPO_PATH=/path/to/remote-view/gsplat
export BACKEND_UPLOADS_DIR=/path/to/remote-view/backend/uploads
python gpu-worker/handler.py
```

---
### Next Steps
- Run the GPU worker with `USE_MOCK=false` to trigger the real pipeline.
- Monitor progress via the frontend stepper UI.

*For any issues, consult the logs in the Processing Logs panel and the backend error output.*
