# GPU Worker + gsplat Engine - Vast.ai / RunPod GPU container
# Packages both the orchestration worker (gpu-worker) and rendering engine (gsplat).
#
# Build from repository root:
#   docker build -f gpu-worker/Dockerfile -t YOUR_DOCKERHUB_USERNAME/remote-view-worker:latest .

FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

WORKDIR /workspace

# Install system dependencies, Python 3.10, COLMAP, and media libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    colmap \
    curl \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN python3.10 -m pip install --upgrade pip

# Install PyTorch with CUDA 12.8 support
RUN python3.10 -m pip install torch==2.10.0 \
    --index-url https://download.pytorch.org/whl/cu128

# Copy worker requirements and install Python dependencies
COPY gpu-worker/requirements.txt ./requirements.txt
RUN python3.10 -m pip install --no-cache-dir -r requirements.txt

# Copy worker and modified gsplat source code
COPY gpu-worker/ ./gpu-worker/
COPY gsplat/ ./gsplat/

# Install local modified gsplat engine and trainer libraries
RUN python3.10 -m pip install -e /workspace/gsplat
RUN cd /workspace/gsplat && \
    python3.10 -m pip install -r examples/requirements.txt --no-build-isolation && \
    python3.10 -m pip install -e libs/scene -e libs/stage

# Create workspace directories
RUN mkdir -p /workspace/data/uploads /workspace/data/output

# Environment configuration
ENV HOST=0.0.0.0
ENV PORT=8080
ENV WORK_DIR=/workspace/data
ENV GSPLAT_REPO_PATH=/workspace/gsplat
ENV PYTHONPATH=/workspace/gsplat:$PYTHONPATH
ENV USE_MOCK=false

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:8080/health || exit 1

WORKDIR /workspace/gpu-worker
CMD ["python3.10", "handler.py"]