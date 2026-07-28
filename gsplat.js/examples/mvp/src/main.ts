import * as SPLAT from "gsplat";

const API_BASE = "http://localhost:3001";

// DOM Elements
const apiStatusBadge = document.getElementById("api-status-badge") as HTMLElement;
const dropZone = document.getElementById("drop-zone") as HTMLElement;
const fileInput = document.getElementById("file-input") as HTMLInputElement;
const uploadProgressContainer = document.getElementById("upload-progress-container") as HTMLElement;
const uploadProgressFill = document.getElementById("upload-progress-fill") as HTMLElement;
const uploadProgressText = document.getElementById("upload-progress-text") as HTMLElement;
const jobsList = document.getElementById("jobs-list") as HTMLElement;
const logsConsole = document.getElementById("logs-console") as HTMLElement;
const activeSceneTitle = document.getElementById("active-scene-title") as HTMLElement;
const activeSceneId = document.getElementById("active-scene-id") as HTMLElement;
const canvas = document.getElementById("canvas") as HTMLCanvasElement;
const viewerOverlay = document.getElementById("viewer-overlay") as HTMLElement;
const viewerOverlayText = document.getElementById("viewer-overlay-text") as HTMLElement;
const viewerProgressIndicator = document.getElementById("viewer-progress-indicator") as HTMLProgressElement;
const btnCapture = document.getElementById("btn-capture") as HTMLButtonElement;

// Modal Elements
const checkoutModal = document.getElementById("checkout-modal") as HTMLElement;
const btnCloseCheckout = document.getElementById("btn-close-checkout") as HTMLButtonElement;
const btnPayNow = document.getElementById("btn-pay-now") as HTMLButtonElement;

// Global State
let activeJobId: string | null = null;
let currentJobs: any[] = [];
let pollingInterval: any = null;
let renderer: SPLAT.WebGLRenderer | null = null;
let scene: SPLAT.Scene | null = null;
let camera: SPLAT.Camera | null = null;
let controls: SPLAT.OrbitControls | null = null;
let captureOnNextFrame = false;
let isRenderLoopRunning = false;

// Initialize 3D Engine
function initEngine() {
    if (renderer) return;

    scene = new SPLAT.Scene();
    camera = new SPLAT.Camera();
    renderer = new SPLAT.WebGLRenderer(canvas);
    
    // We pass false as 6th param to disable built-in OrbitControls keyboard listeners
    // to prevent dual-firing with our game-like step key handlers.
    controls = new SPLAT.OrbitControls(camera, renderer.canvas, 0.5, 0.5, 5, false);

    // Dynamic resize handler
    const handleResize = () => {
        if (renderer && canvas) {
            renderer.setSize(canvas.clientWidth, canvas.clientHeight);
        }
    };
    handleResize();
    window.addEventListener("resize", handleResize);

    // Setup Custom Game-like Keyboard step-by-step navigation
    setupKeyboardControls();
}

function setupKeyboardControls() {
    window.addEventListener("keydown", (e: KeyboardEvent) => {
        if (!camera || !controls || !renderer) return;

        // Obtain rotation matrix buffers
        const R = SPLAT.Matrix3.RotationFromQuaternion(camera.rotation).buffer;
        
        // Define direction vectors from view matrix columns
        const forward = new Vector3Helper(-R[2], -R[5], -R[8]).normalize();
        const right = new Vector3Helper(R[0], R[3], R[6]).normalize();
        const up = new Vector3Helper(R[1], R[4], R[7]).normalize();

        const stepSize = 0.4; // Step displacement in meters
        const rotationStep = 0.08; // Rotation step in radians
        
        let moved = false;
        let rotated = false;

        const eulerRotation = camera.rotation.toEuler();
        let pitch = eulerRotation.x;
        let yaw = eulerRotation.y;

        // Move Controls (WASD / QE)
        if (e.code === "KeyW") {
            camera.position = camera.position.subtract(forward.multiply(stepSize));
            moved = true;
        }
        if (e.code === "KeyS") {
            camera.position = camera.position.add(forward.multiply(stepSize));
            moved = true;
        }
        if (e.code === "KeyA") {
            camera.position = camera.position.subtract(right.multiply(stepSize));
            moved = true;
        }
        if (e.code === "KeyD") {
            camera.position = camera.position.add(right.multiply(stepSize));
            moved = true;
        }
        if (e.code === "KeyQ") {
            camera.position = camera.position.add(up.multiply(stepSize));
            moved = true;
        }
        if (e.code === "KeyE") {
            camera.position = camera.position.subtract(up.multiply(stepSize));
            moved = true;
        }

        // Camera Look/Turn Controls (Arrows or specific tilt bindings)
        if (e.code === "ArrowLeft") {
            yaw += rotationStep;
            rotated = true;
        }
        if (e.code === "ArrowRight") {
            yaw -= rotationStep;
            rotated = true;
        }
        if (e.code === "ArrowUp") {
            pitch += rotationStep;
            rotated = true;
        }
        if (e.code === "ArrowDown") {
            pitch -= rotationStep;
            rotated = true;
        }

        if (rotated) {
            camera.rotation = SPLAT.Quaternion.FromEuler(new SPLAT.Vector3(pitch, yaw, 0));
        }

        if (moved || rotated) {
            // Trigger visual frame render update
            controls.update();
        }
    });
}

// Custom wrapper to manipulate Vector3 structures inside main.ts easily
class Vector3Helper {
    x: number;
    y: number;
    z: number;
    constructor(x: number, y: number, z: number) {
        this.x = x;
        this.y = y;
        this.z = z;
    }
    normalize() {
        const mag = Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z);
        if (mag === 0) return this;
        return new Vector3Helper(this.x / mag, this.y / mag, this.z / mag);
    }
    multiply(val: number) {
        return new SPLAT.Vector3(this.x * val, this.y * val, this.z * val);
    }
}

// WebGL Screenshot logic
btnCapture.addEventListener("click", () => {
    if (!renderer) return;
    captureOnNextFrame = true;
});

// Render Loop controller
function startRenderLoop() {
    if (isRenderLoopRunning) return;
    isRenderLoopRunning = true;

    const frame = () => {
        if (!renderer || !scene || !camera || !controls) {
            isRenderLoopRunning = false;
            return;
        }

        controls.update();
        renderer.render(scene, camera);

        // Perform canvas capture in sync with rendering frame tick to preserve WebGL buffer
        if (captureOnNextFrame) {
            captureOnNextFrame = false;
            const dataUrl = canvas.toDataURL("image/png");
            const link = document.createElement("a");
            link.download = `splat-viewport-${activeJobId || "scene"}.png`;
            link.href = dataUrl;
            link.click();
        }

        requestAnimationFrame(frame);
    };

    requestAnimationFrame(frame);
}

// API Functions
async function checkBackendStatus(): Promise<boolean> {
    try {
        const res = await fetch(`${API_BASE}/api/jobs`);
        if (res.ok) {
            apiStatusBadge.innerHTML = `<span class="status-indicator online"></span> Backend Online`;
            return true;
        }
    } catch (e) {}
    apiStatusBadge.innerHTML = `<span class="status-indicator offline"></span> Backend Offline`;
    return false;
}

async function loadJobs() {
    try {
        const res = await fetch(`${API_BASE}/api/jobs`);
        if (!res.ok) return;
        const jobs = await res.json();
        currentJobs = jobs;
        renderJobsList();
        
        // Update console logs if an active job is selected
        if (activeJobId) {
            const currentJob = jobs.find((j: any) => j.id === activeJobId);
            if (currentJob) {
                updateLogsView(currentJob);
            }
        }
    } catch (e) {
        console.error("Error loading jobs:", e);
    }
}

function renderJobsList() {
    if (currentJobs.length === 0) {
        jobsList.innerHTML = `<div class="no-jobs">No training jobs yet.</div>`;
        return;
    }

    jobsList.innerHTML = currentJobs
        .map((job) => {
            const isActive = job.id === activeJobId ? "active" : "";
            const progressPct = job.progress.toFixed(0);
            
            // Check status for custom UI elements
            const showPayBtn = job.status === "PENDING_PAYMENT";
            const statusLabel = job.status.replace("PROCESSING_", "");

            return `
                <div class="job-card ${isActive}" data-id="${job.id}">
                    <div class="job-card-header">
                        <span class="job-id">${job.id}</span>
                        <span class="badge ${job.status.toLowerCase()}">${statusLabel}</span>
                    </div>
                    <div class="job-card-meta">
                        <span>Created: ${new Date(job.createdAt).toLocaleTimeString()}</span>
                    </div>
                    <div class="job-card-progress">
                        <div class="job-progress-wrapper">
                            <div class="job-progress-fill" style="width: ${progressPct}%;"></div>
                        </div>
                        <div class="job-progress-label">
                            <span>Progress</span>
                            <span>${progressPct}%</span>
                        </div>
                    </div>
                    ${showPayBtn ? `<button class="btn-pay-action" data-pay-id="${job.id}">💳 Checkout & Launch</button>` : ""}
                </div>
            `;
        })
        .join("");

    // Bind event listeners to dynamically rendered items
    document.querySelectorAll(".job-card").forEach((card) => {
        card.addEventListener("click", (e) => {
            const target = e.target as HTMLElement;
            if (target.classList.contains("btn-pay-action")) return; // Don't trigger card selection on checkout click
            
            const jobId = card.getAttribute("data-id")!;
            selectJob(jobId);
        });
    });

    document.querySelectorAll(".btn-pay-action").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const payJobId = btn.getAttribute("data-pay-id")!;
            triggerCheckout(payJobId);
        });
    });
}

function updateLogsView(job: any) {
    logsConsole.textContent = job.logs || "No logs available.";
    logsConsole.scrollTop = logsConsole.scrollHeight; // Auto-scroll to bottom
}

// Select a job to inspect / view 3D splats
async function selectJob(jobId: string) {
    activeJobId = jobId;
    
    // Highlight active card
    document.querySelectorAll(".job-card").forEach((card) => {
        if (card.getAttribute("data-id") === jobId) {
            card.classList.add("active");
        } else {
            card.classList.remove("active");
        }
    });

    const job = currentJobs.find((j) => j.id === jobId);
    if (!job) return;

    activeSceneTitle.textContent = `Job Splat View`;
    activeSceneId.textContent = job.id;
    updateLogsView(job);

    if (job.status === "COMPLETED" && job.splatPath) {
        initEngine();
        loadSplatScene(`${API_BASE}${job.splatPath}`);
    } else {
        // Hide canvas and show details
        viewerOverlayText.textContent = `Training in progress... Status: ${job.status.replace("PROCESSING_", "")} (${job.progress.toFixed(0)}%)`;
        viewerProgressIndicator.style.display = "block";
        viewerProgressIndicator.value = job.progress;
        viewerOverlay.style.display = "flex";
    }
}

// Load .splat model into scene
async function loadSplatScene(url: string) {
    if (!scene || !renderer) return;

    // Reset current active scene
    scene.reset();
    
    viewerOverlayText.textContent = "Downloading 3D splat file...";
    viewerProgressIndicator.style.display = "block";
    viewerProgressIndicator.value = 0;
    viewerOverlay.style.display = "flex";

    try {
        await SPLAT.Loader.LoadAsync(url, scene, (progress: number) => {
            viewerProgressIndicator.value = progress * 100;
            viewerOverlayText.textContent = `Loading 3D scene: ${(progress * 100).toFixed(0)}%`;
        });
        
        viewerOverlay.style.display = "none";
        startRenderLoop();
    } catch (e: any) {
        console.error("Failed to load splat scene:", e);
        viewerOverlayText.textContent = `Rendering error: ${e.message}`;
        viewerProgressIndicator.style.display = "none";
    }
}

// Upload Handling
dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("active");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("active");
});

dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("active");
    if (e.dataTransfer && e.dataTransfer.files.length > 0) {
        uploadFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length > 0) {
        uploadFile(fileInput.files[0]);
    }
});

function uploadFile(file: File) {
    if (!file.name.endsWith(".zip")) {
        alert("Please upload a .zip file containing images.");
        return;
    }

    const formData = new FormData();
    formData.append("images", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/jobs`, true);

    uploadProgressContainer.style.display = "block";
    
    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const percent = (e.loaded / e.total) * 100;
            uploadProgressFill.style.width = `${percent}%`;
            uploadProgressText.textContent = `Uploading: ${percent.toFixed(0)}%`;
        }
    };

    xhr.onload = () => {
        uploadProgressContainer.style.display = "none";
        uploadProgressFill.style.width = "0%";
        if (xhr.status === 200) {
            const job = JSON.parse(xhr.responseText);
            loadJobs().then(() => {
                selectJob(job.id);
            });
        } else {
            alert("Upload failed: " + xhr.responseText);
        }
    };

    xhr.onerror = () => {
        uploadProgressContainer.style.display = "none";
        alert("Network error during file upload.");
    };

    xhr.send(formData);
}

// Payment/Checkout Modal simulation
let checkoutTargetJobId: string | null = null;

function triggerCheckout(jobId: string) {
    checkoutTargetJobId = jobId;
    checkoutModal.style.display = "flex";
}

btnCloseCheckout.addEventListener("click", () => {
    checkoutModal.style.display = "none";
    checkoutTargetJobId = null;
});

btnPayNow.addEventListener("click", async () => {
    if (!checkoutTargetJobId) return;

    try {
        btnPayNow.disabled = true;
        btnPayNow.textContent = "Processing payment...";
        
        const res = await fetch(`${API_BASE}/api/jobs/${checkoutTargetJobId}/start`, {
            method: "POST",
        });

        if (res.ok) {
            checkoutModal.style.display = "none";
            checkoutTargetJobId = null;
            await loadJobs();
        } else {
            alert("Failed to start job: " + (await res.text()));
        }
    } catch (e) {
        alert("Connection error starting job.");
    } finally {
        btnPayNow.disabled = false;
        btnPayNow.textContent = "Pay $9.00 & Launch GPU";
    }
});

// Initialization
async function init() {
    const isOnline = await checkBackendStatus();
    if (isOnline) {
        await loadJobs();
    }
    
    // Poll for status updates
    pollingInterval = setInterval(async () => {
        const online = await checkBackendStatus();
        if (online) {
            await loadJobs();
        }
    }, 2000);
}

init();
