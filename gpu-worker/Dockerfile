
# GPU Worker + gsplat Engine - Vast.ai / RunPod GPU container
#
# Build from repository root:
# docker build -f gpu-worker/Dockerfile \
#   -t YOUR_DOCKERHUB_USERNAME/remote-view-worker:latest .

FROM nvidia/cuda:13.0.0-devel-ubuntu22.04

WORKDIR /workspace

# ------------------------------------------------------------
# CUDA environment
# ------------------------------------------------------------

ENV CUDA_HOME=/usr/local/cuda
ENV PATH=/usr/local/cuda/bin:${PATH}
ENV LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH}

RUN nvcc --version

# ------------------------------------------------------------
# System dependencies
# ------------------------------------------------------------

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Africa/Nairobi


RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ninja-build \
    git \
    curl \
    pkg-config \
    python3.10 \
    python3.10-dev \
    python3-pip \
    gcc-12 \
    g++-12 \
    libboost-program-options-dev \
    libboost-filesystem-dev \
    libboost-graph-dev \
    libboost-system-dev \
    libeigen3-dev \
    libopenimageio-dev \
    openimageio-tools \
    libopenexr-dev \
    libopencv-dev \
    libmetis-dev \
    libgoogle-glog-dev \
    libgflags-dev \
    libgtest-dev \
    libgmock-dev \
    libsqlite3-dev \
    libglew-dev \
    libqt5opengl5-dev \
    qtbase5-dev \
    libqt5svg5-dev \
    libcgal-dev \
    libceres-dev \
    libsuitesparse-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    libatlas-base-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ffmpeg \
    libglm-dev \
    xvfb \
    xauth \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Verify OpenCV development files
# ------------------------------------------------------------
# OpenImageIO's CMake target expects this directory.
# Fail early if the system OpenCV development package did not
# install correctly.

RUN test -d /usr/include/opencv4 \
    && test -f /usr/include/opencv4/opencv2/core.hpp \
    && echo "OpenCV development headers found: /usr/include/opencv4"

# ------------------------------------------------------------
# Modern CMake & Pip
# ------------------------------------------------------------

RUN python3.10 -m pip install --no-cache-dir --upgrade pip cmake

# ------------------------------------------------------------
# CUDA compiler compatibility for Ubuntu 22.04
# ------------------------------------------------------------

ENV CC=/usr/bin/gcc-12
ENV CXX=/usr/bin/g++-12
ENV CUDAHOSTCXX=/usr/bin/g++-12

RUN test -x /usr/bin/gcc-12 && \
    test -x /usr/bin/g++-12 && \
    /usr/bin/gcc-12 --version && \
    /usr/bin/g++-12 --version && \
    nvcc --version

# ------------------------------------------------------------
# Build COLMAP with CUDA support
# ------------------------------------------------------------

RUN git clone \
    --branch 4.2.0 \
    --depth 1 \
    https://github.com/colmap/colmap.git \
    /tmp/colmap

WORKDIR /tmp/colmap/build

RUN cmake .. \
    -GNinja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCUDA_ENABLED=ON \
    -DCMAKE_CUDA_ARCHITECTURES="80;86;89;90" \
    -DCOLMAP_HASH_MAP_BACKEND=STD \
    -DCMAKE_INSTALL_PREFIX=/usr/local

RUN ninja -j"$(nproc)"

RUN ninja install

# Make sure the CUDA-enabled COLMAP binary is the one we use.
RUN which colmap && colmap -h

# Verify that the COLMAP binary can see CUDA-related libraries.
RUN ldd "$(which colmap)" | grep -E "cuda|cudart|curand|cublas" || true

WORKDIR /workspace

RUN rm -rf /tmp/colmap

# ------------------------------------------------------------
# Python
# ------------------------------------------------------------

# PyTorch & Torchvision CUDA 13.0
RUN python3.10 -m pip install \
    torch==2.10.0 \
    torchvision \
    --index-url https://download.pytorch.org/whl/cu130

# ------------------------------------------------------------
# GPU worker Python dependencies
# ------------------------------------------------------------

COPY gpu-worker/requirements.txt ./requirements.txt

RUN python3.10 -m pip install \
    --no-cache-dir \
    -r requirements.txt

# ------------------------------------------------------------
# Copy application and gsplat
# ------------------------------------------------------------

COPY gpu-worker/ ./gpu-worker/
COPY gsplat/ ./gsplat/

# ------------------------------------------------------------
# CUDA architectures for gsplat
# ------------------------------------------------------------

ENV TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0"

# ------------------------------------------------------------
# Install local gsplat engine
# ------------------------------------------------------------

RUN python3.10 -m pip install -e /workspace/gsplat

RUN python3.10 -m pip install -e /workspace/gsplat/libs/scene

RUN python3.10 -m pip install -e /workspace/gsplat/libs/stage

# ------------------------------------------------------------
# Precompile gsplat CUDA extension
# ------------------------------------------------------------

RUN python3.10 -c \
    "from gsplat.cuda._backend import _C; print('gsplat CUDA extension pre-compiled successfully!')"

# ------------------------------------------------------------
# Worker workspace
# ------------------------------------------------------------

RUN mkdir -p /workspace/data

# ------------------------------------------------------------
# Runtime environment
# ------------------------------------------------------------

ENV HOST=0.0.0.0
ENV PORT=8080
ENV WORK_DIR=/workspace/data
ENV GSPLAT_REPO_PATH=/workspace/gsplat
ENV PYTHONPATH=/workspace/gsplat
ENV USE_MOCK=false
ENV QT_QPA_PLATFORM=offscreen

# Explicitly request CUDA for COLMAP.
ENV COLMAP_USE_GPU=1

EXPOSE 8080

# ------------------------------------------------------------
# Container health check
# ------------------------------------------------------------

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=10s \
    CMD curl -f http://localhost:8080/health || exit 1

# ------------------------------------------------------------
# Start worker
# ------------------------------------------------------------

WORKDIR /workspace/gpu-worker

CMD ["python3.10", "handler.py"]