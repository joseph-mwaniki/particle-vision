import {
  checkHealth,
  listJobs,
  uploadImages,
  startTraining,
  assetUrl,
  type Job,
} from "./api";
import { SplatViewer } from "./viewer/viewer";
import { PipelineStepper, type JobStatus } from "./components/Stepper";

const apiStatusBadge = document.getElementById("api-status-badge")!;
const dropZone = document.getElementById("drop-zone")!;
const fileInput = document.getElementById("file-input") as HTMLInputElement;
const uploadProgressContainer = document.getElementById("upload-progress-container")!;
const uploadProgressFill = document.getElementById("upload-progress-fill")!;
const uploadProgressText = document.getElementById("upload-progress-text")!;
const jobsList = document.getElementById("jobs-list")!;
const logsConsole = document.getElementById("logs-console")!;
const activeSceneTitle = document.getElementById("active-scene-title")!;
const activeSceneId = document.getElementById("active-scene-id")!;
const canvas = document.getElementById("canvas") as HTMLCanvasElement;
const viewerOverlay = document.getElementById("viewer-overlay")!;
const viewerOverlayText = document.getElementById("viewer-overlay-text")!;
const viewerProgressIndicator = document.getElementById("viewer-progress-indicator") as HTMLProgressElement;
const btnCapture = document.getElementById("btn-capture") as HTMLButtonElement;
const btnLoadSample = document.getElementById("btn-load-sample") as HTMLButtonElement;
const btnTrain = document.getElementById("btn-train") as HTMLButtonElement;
const btnDeps = document.getElementById("btn-deps") as HTMLButtonElement;
const depsModal = document.getElementById("deps-modal")!;
const depsModalClose = document.getElementById("deps-modal-close")!;
const depsContent = document.getElementById("deps-content")!;

const stepper = new PipelineStepper("pipeline-stepper");

let activeJobId: string | null = null;
let currentJobs: Job[] = [];
let viewer: SplatViewer | null = null;
let depsLoaded = false;

function initViewer(): SplatViewer {
  if (!viewer) {
    viewer = new SplatViewer({
      canvas,
      onProgress: (message, progress) => {
        viewerOverlayText.textContent = message;
        viewerProgressIndicator.value = progress;
        viewerProgressIndicator.style.display = "block";
        viewerOverlay.style.display = "flex";
      },
      onReady: () => {
        viewerOverlay.style.display = "none";
      },
      onError: (message) => {
        viewerOverlayText.textContent = message;
        viewerProgressIndicator.style.display = "none";
      },
    });
  }
  return viewer;
}

function updateStepper(job: Job | undefined): void {
  if (!job || job.status === "PENDING") {
    stepper.update("PENDING" as JobStatus, null);
    return;
  }
  stepper.update(job.status as JobStatus, job.logs);
}

async function updateBackendStatus(): Promise<boolean> {
  const health = await checkHealth();
  if (health) {
    apiStatusBadge.innerHTML = `<span class="status-indicator online"></span> Backend Online`;
    return true;
  }
  apiStatusBadge.innerHTML = `<span class="status-indicator offline"></span> Backend Offline`;
  return false;
}

async function loadJobs(): Promise<void> {
  try {
    currentJobs = await listJobs();
    renderJobsList();
    if (activeJobId) {
      const job = currentJobs.find((j) => j.id === activeJobId);
      if (job) {
        updateLogsView(job);
        updateStepper(job);
      }
    }
  } catch (e) {
    console.error("Error loading jobs:", e);
  }
}

function renderJobsList(): void {
  if (currentJobs.length === 0) {
    jobsList.innerHTML = `<div class="no-jobs">No training jobs yet.</div>`;
    return;
  }

  jobsList.innerHTML = currentJobs
    .map((job) => {
      const isActive = job.id === activeJobId ? "active" : "";
      const progressPct = job.progress.toFixed(0);
      const statusLabel = job.status.replace("PROCESSING_", "");
      const canTrain = job.status === "PENDING" || job.status === "FAILED";

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
          ${canTrain ? `<button class="btn-train-action" data-train-id="${job.id}">Start Training</button>` : ""}
        </div>
      `;
    })
    .join("");

  document.querySelectorAll(".job-card").forEach((card) => {
    card.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (target.classList.contains("btn-train-action")) return;
      selectJob(card.getAttribute("data-id")!);
    });
  });

  document.querySelectorAll(".btn-train-action").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const jobId = btn.getAttribute("data-train-id")!;
      await handleTrain(jobId);
    });
  });
}

function updateLogsView(job: Job): void {
  logsConsole.textContent = job.logs || "No logs available.";
  logsConsole.scrollTop = logsConsole.scrollHeight;
}

async function selectJob(jobId: string): Promise<void> {
  activeJobId = jobId;
  btnTrain.style.display = "none";

  document.querySelectorAll(".job-card").forEach((card) => {
    card.classList.toggle("active", card.getAttribute("data-id") === jobId);
  });

  const job = currentJobs.find((j) => j.id === jobId);
  if (!job) return;

  activeSceneTitle.textContent = "Job Splat View";
  activeSceneId.textContent = job.id;
  updateLogsView(job);
  updateStepper(job);

  if (job.status === "PENDING" || job.status === "FAILED") {
    btnTrain.style.display = "inline-flex";
    btnTrain.onclick = () => handleTrain(jobId);
  }

  if (job.status === "COMPLETED" && job.splatPath) {
    const v = initViewer();
    await v.loadSplat(assetUrl(job.splatPath));
    if (job.collisionPath) {
      await v.loadCollisionMesh(assetUrl(job.collisionPath));
    }
  } else if (job.status === "FAILED") {
    viewerOverlayText.textContent = job.logs?.split("\n").filter((l) => l.includes("ERROR")).pop()?.replace(/^.*ERROR:\s*/, "") || "Training failed";
    viewerProgressIndicator.style.display = "none";
    viewerOverlay.style.display = "flex";
  } else if (job.status !== "COMPLETED") {
    const stage = job.status.replace("PROCESSING_", "");
    viewerOverlayText.textContent = `Training in progress — ${stage} (${job.progress.toFixed(0)}%)`;
    viewerProgressIndicator.style.display = "block";
    viewerProgressIndicator.value = job.progress;
    viewerOverlay.style.display = "flex";
  }
}

async function handleTrain(jobId: string): Promise<void> {
  try {
    btnTrain.disabled = true;
    btnTrain.textContent = "Starting...";
    await startTraining(jobId);
    await loadJobs();
    selectJob(jobId);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Training failed";
    alert(msg);
  } finally {
    btnTrain.disabled = false;
    btnTrain.textContent = "Start Training";
  }
}

async function loadDependenciesGuide(): Promise<void> {
  if (depsLoaded) return;
  try {
    const res = await fetch("/DEPENDENCIES.md");
    depsContent.textContent = res.ok ? await res.text() : "Could not load DEPENDENCIES.md";
    depsLoaded = true;
  } catch {
    depsContent.textContent = "Could not load setup guide. See DEPENDENCIES.md in the project root.";
  }
}

function openDepsModal(): void {
  loadDependenciesGuide();
  depsModal.style.display = "flex";
}

function closeDepsModal(): void {
  depsModal.style.display = "none";
}

btnDeps.addEventListener("click", openDepsModal);
depsModalClose.addEventListener("click", closeDepsModal);
depsModal.addEventListener("click", (e) => {
  if (e.target === depsModal) closeDepsModal();
});

// Upload handling
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("active"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("active"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("active");
  if (e.dataTransfer?.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files?.length) uploadFile(fileInput.files[0]);
});

async function uploadFile(file: File): Promise<void> {
  if (!file.name.endsWith(".zip")) {
    alert("Please upload a .zip file containing images.");
    return;
  }

  uploadProgressContainer.style.display = "block";
  try {
    const job = await uploadImages(file, (pct) => {
      uploadProgressFill.style.width = `${pct}%`;
      uploadProgressText.textContent = `Uploading: ${pct.toFixed(0)}%`;
    });
    uploadProgressContainer.style.display = "none";
    uploadProgressFill.style.width = "0%";
    await loadJobs();
    selectJob(job.id);
  } catch (e: unknown) {
    uploadProgressContainer.style.display = "none";
    const msg = e instanceof Error ? e.message : "Upload failed";
    alert(msg);
  }
}

btnLoadSample.addEventListener("click", async () => {
  const v = initViewer();
  activeSceneTitle.textContent = "Sample Scene";
  activeSceneId.textContent = "bonsai.splat";
  stepper.update("PENDING" as JobStatus, null);
  await v.loadSplat("/samples/bonsai.splat");
});

btnCapture.addEventListener("click", () => {
  viewer?.captureScreenshot(`splat-viewport-${activeJobId || "sample"}.png`);
});

async function init(): Promise<void> {
  if (await updateBackendStatus()) {
    await loadJobs();
  }
  setInterval(async () => {
    if (await updateBackendStatus()) {
      await loadJobs();
      if (activeJobId) {
        const job = currentJobs.find((j) => j.id === activeJobId);
        if (job?.status === "COMPLETED" && job.splatPath) {
          const overlayVisible = viewerOverlay.style.display !== "none";
          if (overlayVisible) selectJob(activeJobId);
        }
      }
    }
  }, 2000);
}

init();
