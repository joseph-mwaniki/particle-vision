# GPU Worker + gsplat Engine - RunPod-ready container
#
# This image packages BOTH the orchestration layer (gpu-worker) 
# AND the rendering engine (gsplat) together.
#
# IMPORTANT: Build from repository root, NOT from inside gpu-worker/
#
# Build command:
#   cd remote-view
#   docker build -f gpu-worker/Dockerfile -t remote-view-worker:latest .
#
# Verified dependency versions (from gsplat/.github/workflows/building.yml):
#   Python 3.10
#   PyTorch 2.10.0 + CUDA 12.8 (cu128)
#   gsplat 1.5.3 (modified local version)

# ============================================================
# PHASE 1: Placeholder worker (no CUDA, no real training)
# ============================================================
FROM python:3.10-slim

WORKDIR /workspace

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy and install GPU worker dependencies
COPY gpu-worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy GPU worker source code
COPY gpu-worker/ ./gpu-worker/

# Copy the ENTIRE gsplat engine (your modified version)
COPY gsplat/ ./gsplat/

# Create workspace directories
RUN mkdir -p /workspace/data/uploads \
             /workspace/data/output

# Set environment variables for the worker to find gsplat
ENV HOST=0.0.0.0
ENV PORT=8080
ENV WORK_DIR=/workspace/data
ENV GSPLAT_REPO_PATH=/workspace/gsplat
ENV PYTHONPATH=/workspace/gsplat:$PYTHONPATH
ENV USE_MOCK=true  # Keep as true until training is ready

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
    CMD curl -f http://localhost:8080/health || exit 1

# Run from the gpu-worker directory
WORKDIR /workspace/gpu-worker

CMD ["python", "handler.py"]


# ============================================================
# PHASE 2: Real GPU training (uncomment when ready)
# ============================================================
# FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04
# 
# WORKDIR /workspace
# 
# # System dependencies
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     python3.10 \
#     python3-pip \
#     colmap \
#     curl \
#     git \
#     libgl1-mesa-glx \
#     libglib2.0-0 \
#     ffmpeg \
#     && rm -rf /var/lib/apt/lists/*
# 
# # Install PyTorch with CUDA
# RUN pip install torch==2.10.0 \
#     --index-url https://download.pytorch.org/whl/cu128
# 
# # Copy GPU worker dependencies and source
# COPY gpu-worker/requirements.txt ./requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt
# COPY gpu-worker/ ./gpu-worker/
# 
# # Copy and install LOCAL modified gsplat (NOT the public wheel!)
# COPY gsplat/ ./gsplat/
# RUN pip install -e /workspace/gsplat
# 
# # Install example trainer dependencies (from gsplat/examples/requirements.txt)
# RUN cd /workspace/gsplat && \
#     pip install -r examples/requirements.txt --no-build-isolation && \
#     python -m pip install -e libs/scene -e libs/stage
# 
# # Create workspace directories
# RUN mkdir -p /workspace/data/uploads \
#              /workspace/data/output
# 
# # Environment variables
# ENV HOST=0.0.0.0
# ENV PORT=8080
# ENV WORK_DIR=/workspace/data
# ENV GSPLAT_REPO_PATH=/workspace/gsplat
# ENV PYTHONPATH=/workspace/gsplat:$PYTHONPATH
# ENV USE_MOCK=false
# 
# EXPOSE 8080
# 
# HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
#     CMD curl -f http://localhost:8080/health || exit 1
# 
# WORKDIR /workspace/gpu-worker
# CMD ["python", "handler.py"]