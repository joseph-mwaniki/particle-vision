# GPU Worker + gsplat Engine - Vast.ai / RunPod GPU container
# Packages both the orchestration worker (gpu-worker) and rendering engine (gsplat).
#
# Build from repository root:
#   docker build -f gpu-worker/Dockerfile -t YOUR_DOCKERHUB_USERNAME/remote-view-worker:latest .

FROM nvidia/cuda:13.0.0-devel-ubuntu22.04

WORKDIR /workspace

# Set CUDA environment paths
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=/usr/local/cuda/bin:${PATH}
ENV LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH}

# Verify nvcc compiler is available
RUN nvcc --version

# Install system dependencies, Python 3.10, development headers, COLMAP, and media libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3.10 \
    python3.10-dev \
    python3-pip \
    colmap \
    curl \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ffmpeg \
    ninja-build \
    libglm-dev \
    xvfb \
    xauth \
    && rm -rf /var/lib/apt/lists/*

RUN python3.10 -m pip install --upgrade pip

# Install PyTorch with CUDA 13.0 support
RUN python3.10 -m pip install torch==2.10.0 \
    --index-url https://download.pytorch.org/whl/cu130

# Copy worker requirements and install Python dependencies
COPY gpu-worker/requirements.txt ./requirements.txt
RUN python3.10 -m pip install --no-cache-dir -r requirements.txt

# Copy worker and modified gsplat source code
COPY gpu-worker/ ./gpu-worker/
COPY gsplat/ ./gsplat/

# Set CUDA architectures for PyTorch C++ extensions to prevent IndexError
ENV TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0"

# Install local modified gsplat engine and trainer libraries
RUN python3.10 -m pip install -e /workspace/gsplat

# Install scene and stage libraries (skip examples to avoid dependency conflicts)
RUN python3.10 -m pip install -e /workspace/gsplat/libs/scene
RUN python3.10 -m pip install -e /workspace/gsplat/libs/stage

# Pre-compile gsplat CUDA extension during docker build to eliminate 6+ minute runtime JIT delay
RUN python3.10 -c "from gsplat.cuda._backend import _C; print('gsplat CUDA extension pre-compiled successfully!')"

# Create workspace directories
RUN mkdir -p /workspace/data/uploads /workspace/data/output

# Environment configuration
ENV HOST=0.0.0.0
ENV PORT=8080
ENV WORK_DIR=/workspace/data
ENV GSPLAT_REPO_PATH=/workspace/gsplat
ENV PYTHONPATH=/workspace/gsplat
ENV USE_MOCK=false
ENV QT_QPA_PLATFORM=offscreen

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:8080/health || exit 1

WORKDIR /workspace/gpu-worker
CMD ["python3.10", "handler.py"]