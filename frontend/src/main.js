import { checkHealth, listJobs, uploadImages, startTraining, assetUrl, listSplats, getSplat, createSplat, updateSplat, publishSplat, deleteSplat, } from "./api";
import { SplatViewer } from "./viewer/viewer";
import { PipelineStepper } from "./components/Stepper";
// DOM Elements - Navigation & UI
const appContainer = document.getElementById("app-container");
const mainSidebar = document.getElementById("main-sidebar");
const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
const btnExpandSidebar = document.getElementById("btn-expand-sidebar");
const apiStatusBadge = document.getElementById("api-status-badge");
const tabSplats = document.getElementById("tab-splats");
const tabTrain = document.getElementById("tab-train");
const paneSplats = document.getElementById("pane-splats");
const paneTrain = document.getElementById("pane-train");
// DOM Elements - Splats Library
const splatsList = document.getElementById("splats-list");
const countAll = document.getElementById("count-all");
const countPublished = document.getElementById("count-published");
const countDraft = document.getElementById("count-draft");
const filterPills = document.querySelectorAll(".filter-pills .pill");
const btnNewSplatModal = document.getElementById("btn-new-splat-modal");
// DOM Elements - Jobs & Upload Pipeline
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const uploadProgressContainer = document.getElementById("upload-progress-container");
const uploadProgressFill = document.getElementById("upload-progress-fill");
const uploadProgressText = document.getElementById("upload-progress-text");
const jobsList = document.getElementById("jobs-list");
const logsConsole = document.getElementById("logs-console");
// DOM Elements - Viewer & Actions
const activeSceneTitle = document.getElementById("active-scene-title");
const activeSceneId = document.getElementById("active-scene-id");
const activeSceneBadge = document.getElementById("active-scene-badge");
const canvas = document.getElementById("canvas");
const viewerOverlay = document.getElementById("viewer-overlay");
const viewerOverlayText = document.getElementById("viewer-overlay-text");
const viewerProgressIndicator = document.getElementById("viewer-progress-indicator");
const btnCapture = document.getElementById("btn-capture");
const btnLoadSample = document.getElementById("btn-load-sample");
const btnTrain = document.getElementById("btn-train");
const btnSaveCamera = document.getElementById("btn-save-camera");
const btnShareModal = document.getElementById("btn-share-modal");
const btnClientMode = document.getElementById("btn-client-mode");
// DOM Elements - Showcase Client Banner
const showcaseBanner = document.getElementById("showcase-banner");
const showcaseBannerTitle = document.getElementById("showcase-banner-title");
const showcaseBannerDesc = document.getElementById("showcase-banner-desc");
const showcaseBannerStatus = document.getElementById("showcase-banner-status");
const btnBannerPublish = document.getElementById("btn-banner-publish");
const btnBannerShare = document.getElementById("btn-banner-share");
const btnResetCam = document.getElementById("btn-reset-cam");
const btnFullscreen = document.getElementById("btn-fullscreen");
const btnExitClient = document.getElementById("btn-exit-client");
// DOM Elements - Share Modal
const shareModal = document.getElementById("share-modal");
const shareModalClose = document.getElementById("share-modal-close");
const shareStatusBadge = document.getElementById("share-status-badge");
const btnTogglePublishState = document.getElementById("btn-toggle-publish-state");
const sharePublicUrl = document.getElementById("share-public-url");
const shareDraftUrl = document.getElementById("share-draft-url");
const shareEmbedCode = document.getElementById("share-embed-code");
const btnCopyPublicUrl = document.getElementById("btn-copy-public-url");
const btnCopyDraftUrl = document.getElementById("btn-copy-draft-url");
const btnCopyEmbedCode = document.getElementById("btn-copy-embed-code");
// DOM Elements - Save Splat Modal
const saveSplatModal = document.getElementById("save-splat-modal");
const saveSplatClose = document.getElementById("save-splat-close");
const formSaveSplat = document.getElementById("form-save-splat");
const inputSplatTitle = document.getElementById("input-splat-title");
const inputSplatDesc = document.getElementById("input-splat-desc");
const selectSplatStatus = document.getElementById("select-splat-status");
const btnCancelSaveSplat = document.getElementById("btn-cancel-save-splat");
// DOM Elements - Settings Modal
const settingsModal = document.getElementById("settings-modal");
const settingsModalClose = document.getElementById("settings-modal-close");
const btnApiSettings = document.getElementById("btn-api-settings");
const inputApiKey = document.getElementById("input-api-key");
const btnSaveSettings = document.getElementById("btn-save-settings");
// App State
const stepper = new PipelineStepper("pipeline-stepper");
let activeJobId = null;
let activeSplat = null;
let currentSplats = [];
let currentJobs = [];
let activeFilter = "all";
let viewer = null;
let currentLoadedPath = "/samples/bonsai.splat";
let isClientMode = false;
let userApiKey = localStorage.getItem("pv_api_key") || "";
if (inputApiKey && userApiKey) {
    inputApiKey.value = userApiKey;
}
// ---------------- VIEWER INITIALIZATION ----------------
function initViewer() {
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
// ---------------- BACKEND HEALTH & DATA SYNC ----------------
async function updateBackendStatus() {
    const health = await checkHealth();
    if (health) {
        apiStatusBadge.innerHTML = `<span class="status-indicator online"></span> Backend Online`;
        return true;
    }
    apiStatusBadge.innerHTML = `<span class="status-indicator offline"></span> Backend Offline`;
    return false;
}
async function loadSplatsData() {
    try {
        currentSplats = await listSplats();
        renderSplatsList();
    }
    catch (err) {
        console.error("Failed to load splats database:", err);
    }
}
async function loadJobs() {
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
    }
    catch (e) {
        console.error("Error loading jobs:", e);
    }
}
function updateStepper(job) {
    if (!job || job.status === "PENDING") {
        stepper.update("PENDING", null);
        return;
    }
    stepper.update(job.status, job.logs);
}
// ---------------- SPLAT DB RENDERING ----------------
function renderSplatsList() {
    const allCount = currentSplats.length;
    const pubCount = currentSplats.filter((s) => s.status === "published").length;
    const draftCount = currentSplats.filter((s) => s.status === "draft").length;
    if (countAll)
        countAll.textContent = String(allCount);
    if (countPublished)
        countPublished.textContent = String(pubCount);
    if (countDraft)
        countDraft.textContent = String(draftCount);
    let filtered = currentSplats;
    if (activeFilter === "published") {
        filtered = currentSplats.filter((s) => s.status === "published");
    }
    else if (activeFilter === "draft") {
        filtered = currentSplats.filter((s) => s.status === "draft");
    }
    if (filtered.length === 0) {
        splatsList.innerHTML = `
      <div class="no-jobs">
        No ${activeFilter !== "all" ? activeFilter : ""} 3D scenes found in DB.
      </div>
    `;
        return;
    }
    splatsList.innerHTML = filtered
        .map((splat) => {
        const isActive = activeSplat?.id === splat.id ? "active" : "";
        const isPublished = splat.status === "published";
        const statusClass = isPublished ? "badge-published" : "badge-draft";
        const statusLabel = isPublished ? "Live Published" : "Draft";
        return `
        <div class="splat-card ${isActive}" data-id="${splat.id}">
          <div class="splat-card-header">
            <div class="splat-card-title">${escapeHtml(splat.title)}</div>
            <span class="badge ${statusClass}">${statusLabel}</span>
          </div>
          ${splat.description ? `<p class="splat-card-desc">${escapeHtml(splat.description)}</p>` : ""}
          <div class="splat-card-meta">
            <span>👁️ ${splat.views || 0} views</span>
            <span>${new Date(splat.updatedAt).toLocaleDateString()}</span>
          </div>
          <div class="splat-card-actions">
            <button class="btn btn-sm btn-secondary btn-view-splat" data-splat-id="${splat.id}">View 3D</button>
            <button class="btn btn-sm btn-secondary btn-share-splat" data-splat-id="${splat.id}">🔗 Share</button>
            <button class="btn btn-sm ${isPublished ? "btn-secondary" : "btn-accent"} btn-toggle-publish" data-splat-id="${splat.id}">
              ${isPublished ? "Unpublish" : "Publish"}
            </button>
            <button class="btn-danger-icon btn-delete-splat" data-splat-id="${splat.id}" title="Delete Splat">✕</button>
          </div>
        </div>
      `;
    })
        .join("");
    // Attach event listeners
    document.querySelectorAll(".splat-card").forEach((card) => {
        card.addEventListener("click", (e) => {
            const target = e.target;
            if (target.tagName === "BUTTON")
                return;
            const id = card.getAttribute("data-id");
            selectSplatById(id);
        });
    });
    document.querySelectorAll(".btn-view-splat").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const id = btn.getAttribute("data-splat-id");
            selectSplatById(id);
        });
    });
    document.querySelectorAll(".btn-share-splat").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const id = btn.getAttribute("data-splat-id");
            const splat = currentSplats.find((s) => s.id === id);
            if (splat)
                openShareModal(splat);
        });
    });
    document.querySelectorAll(".btn-toggle-publish").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const id = btn.getAttribute("data-splat-id");
            const splat = currentSplats.find((s) => s.id === id);
            if (!splat)
                return;
            const nextStatus = splat.status === "published" ? "draft" : "published";
            try {
                btn.textContent = "Updating...";
                await publishSplat(id, nextStatus);
                await loadSplatsData();
                if (activeSplat?.id === id) {
                    activeSplat.status = nextStatus;
                    updateActiveSceneHeader();
                }
            }
            catch (err) {
                alert(err instanceof Error ? err.message : "Failed to update publish status");
            }
        });
    });
    document.querySelectorAll(".btn-delete-splat").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const id = btn.getAttribute("data-splat-id");
            if (!confirm("Are you sure you want to delete this splat from the database?"))
                return;
            try {
                await deleteSplat(id);
                await loadSplatsData();
            }
            catch (err) {
                alert(err instanceof Error ? err.message : "Failed to delete splat");
            }
        });
    });
}
function escapeHtml(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
// ---------------- SELECT & LOAD SPLAT SCENE ----------------
async function selectSplatById(id) {
    const splat = currentSplats.find((s) => s.id === id);
    if (!splat)
        return;
    activeSplat = splat;
    activeJobId = null;
    currentLoadedPath = splat.splatPath;
    updateActiveSceneHeader();
    renderSplatsList();
    const v = initViewer();
    await v.loadSplat(assetUrl(splat.splatPath));
    if (splat.collisionPath) {
        await v.loadCollisionMesh(assetUrl(splat.collisionPath));
    }
}
function updateActiveSceneHeader() {
    if (activeSplat) {
        activeSceneTitle.textContent = activeSplat.title;
        activeSceneId.textContent = `Slug: ${activeSplat.slug}`;
        activeSceneBadge.style.display = "inline-flex";
        activeSceneBadge.className = `badge ${activeSplat.status === "published" ? "badge-published" : "badge-draft"}`;
        activeSceneBadge.textContent = activeSplat.status === "published" ? "Published" : "Draft";
        // Update banner for client mode
        showcaseBannerTitle.textContent = activeSplat.title;
        showcaseBannerDesc.textContent = activeSplat.description || "Interactive 3D Gaussian Splatting showcase";
        showcaseBannerStatus.className = `badge ${activeSplat.status === "published" ? "badge-published" : "badge-draft"}`;
        showcaseBannerStatus.textContent = activeSplat.status === "published" ? "Published" : "Draft Preview";
        if (activeSplat.status === "draft") {
            btnBannerPublish.style.display = "inline-flex";
        }
        else {
            btnBannerPublish.style.display = "none";
        }
    }
    else if (activeJobId) {
        activeSceneTitle.textContent = "Job Splat View";
        activeSceneId.textContent = activeJobId;
        activeSceneBadge.style.display = "none";
    }
    else {
        activeSceneTitle.textContent = "Sample Scene";
        activeSceneId.textContent = "bonsai.splat";
        activeSceneBadge.style.display = "inline-flex";
        activeSceneBadge.className = "badge";
        activeSceneBadge.textContent = "Sample";
    }
}
// ---------------- CLIENT SHOWCASE MODE ----------------
function setClientMode(enabled) {
    isClientMode = enabled;
    if (enabled) {
        mainSidebar.classList.add("collapsed");
        btnExpandSidebar.style.display = "flex";
        showcaseBanner.style.display = "flex";
        btnClientMode.classList.add("btn-accent");
        btnClientMode.classList.remove("btn-secondary");
    }
    else {
        mainSidebar.classList.remove("collapsed");
        btnExpandSidebar.style.display = "none";
        showcaseBanner.style.display = "none";
        btnClientMode.classList.remove("btn-accent");
        btnClientMode.classList.add("btn-secondary");
    }
}
btnClientMode.addEventListener("click", () => {
    setClientMode(!isClientMode);
});
btnExitClient.addEventListener("click", () => {
    setClientMode(false);
});
btnToggleSidebar.addEventListener("click", () => {
    mainSidebar.classList.add("collapsed");
    btnExpandSidebar.style.display = "flex";
});
btnExpandSidebar.addEventListener("click", () => {
    mainSidebar.classList.remove("collapsed");
    btnExpandSidebar.style.display = "none";
});
btnFullscreen.addEventListener("click", () => {
    if (!document.fullscreenElement) {
        appContainer.requestFullscreen().catch(() => { });
    }
    else {
        document.exitFullscreen().catch(() => { });
    }
});
btnResetCam.addEventListener("click", async () => {
    if (activeSplat) {
        await selectSplatById(activeSplat.id);
    }
});
// ---------------- SHARE MODAL ----------------
let modalTargetSplat = null;
function openShareModal(splat) {
    modalTargetSplat = splat;
    const isPub = splat.status === "published";
    shareStatusBadge.className = `badge ${isPub ? "badge-published" : "badge-draft"}`;
    shareStatusBadge.textContent = isPub ? "Published (Live)" : "Draft (Private)";
    btnTogglePublishState.textContent = isPub ? "Switch to Draft Mode" : "🚀 Publish to Public Link";
    btnTogglePublishState.className = `btn btn-sm ${isPub ? "btn-secondary" : "btn-accent"}`;
    const origin = window.location.origin;
    const publicLink = `${origin}/?view=${splat.slug}`;
    const draftLink = `${origin}/?view=${splat.slug}&token=${splat.shareToken}`;
    const embed = `<iframe src="${publicLink}" width="100%" height="600" frameborder="0" allowfullscreen allow="accelerometer; gyroscope; vr"></iframe>`;
    sharePublicUrl.value = isPub ? publicLink : "(Publish scene first to activate public link)";
    shareDraftUrl.value = draftLink;
    shareEmbedCode.value = embed;
    shareModal.style.display = "flex";
}
function closeShareModal() {
    shareModal.style.display = "none";
    modalTargetSplat = null;
}
btnShareModal.addEventListener("click", () => {
    if (activeSplat) {
        openShareModal(activeSplat);
    }
    else {
        // Prompt user to save current scene first
        openSaveModal();
    }
});
btnBannerShare.addEventListener("click", () => {
    if (activeSplat) {
        const origin = window.location.origin;
        const url = activeSplat.status === "published"
            ? `${origin}/?view=${activeSplat.slug}`
            : `${origin}/?view=${activeSplat.slug}&token=${activeSplat.shareToken}`;
        copyToClipboard(url, btnBannerShare, "Copied Link!");
    }
});
btnBannerPublish.addEventListener("click", async () => {
    if (activeSplat) {
        try {
            btnBannerPublish.textContent = "Publishing...";
            await publishSplat(activeSplat.id, "published");
            activeSplat.status = "published";
            await loadSplatsData();
            updateActiveSceneHeader();
            alert("Scene is now published! Share link is live.");
        }
        catch (err) {
            alert(err instanceof Error ? err.message : "Failed to publish");
        }
        finally {
            btnBannerPublish.textContent = "🚀 Publish Now";
        }
    }
});
shareModalClose.addEventListener("click", closeShareModal);
shareModal.addEventListener("click", (e) => {
    if (e.target === shareModal)
        closeShareModal();
});
btnTogglePublishState.addEventListener("click", async () => {
    if (!modalTargetSplat)
        return;
    const nextStatus = modalTargetSplat.status === "published" ? "draft" : "published";
    try {
        btnTogglePublishState.disabled = true;
        btnTogglePublishState.textContent = "Updating...";
        const res = await publishSplat(modalTargetSplat.id, nextStatus);
        modalTargetSplat.status = nextStatus;
        modalTargetSplat.publishedAt = res.splat.publishedAt;
        await loadSplatsData();
        openShareModal(modalTargetSplat);
        if (activeSplat?.id === modalTargetSplat.id) {
            activeSplat.status = nextStatus;
            updateActiveSceneHeader();
        }
    }
    catch (err) {
        alert(err instanceof Error ? err.message : "Failed to update publish status");
    }
    finally {
        btnTogglePublishState.disabled = false;
    }
});
function copyToClipboard(text, button, successText = "Copied!") {
    if (!text || text.startsWith("("))
        return;
    navigator.clipboard.writeText(text).then(() => {
        const orig = button.textContent;
        button.textContent = successText;
        button.style.backgroundColor = "rgba(16, 185, 129, 0.3)";
        setTimeout(() => {
            button.textContent = orig;
            button.style.backgroundColor = "";
        }, 2000);
    });
}
btnCopyPublicUrl.addEventListener("click", () => copyToClipboard(sharePublicUrl.value, btnCopyPublicUrl));
btnCopyDraftUrl.addEventListener("click", () => copyToClipboard(shareDraftUrl.value, btnCopyDraftUrl));
btnCopyEmbedCode.addEventListener("click", () => copyToClipboard(shareEmbedCode.value, btnCopyEmbedCode));
// ---------------- SAVE SPLAT MODAL ----------------
function openSaveModal() {
    inputSplatTitle.value = activeSplat?.title || (activeJobId ? `Job ${activeJobId}` : "Showcase 3D Scene");
    inputSplatDesc.value = activeSplat?.description || "";
    selectSplatStatus.value = "published";
    saveSplatModal.style.display = "flex";
}
function closeSaveModal() {
    saveSplatModal.style.display = "none";
}
btnNewSplatModal.addEventListener("click", openSaveModal);
saveSplatClose.addEventListener("click", closeSaveModal);
btnCancelSaveSplat.addEventListener("click", closeSaveModal);
saveSplatModal.addEventListener("click", (e) => {
    if (e.target === saveSplatModal)
        closeSaveModal();
});
formSaveSplat.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = inputSplatTitle.value.trim();
    const description = inputSplatDesc.value.trim();
    const status = selectSplatStatus.value;
    if (!title)
        return;
    try {
        const submitBtn = document.getElementById("btn-submit-save-splat");
        submitBtn.disabled = true;
        submitBtn.textContent = "Saving to Database...";
        const newSplat = await createSplat({
            title,
            description,
            status,
            splatPath: currentLoadedPath || "/samples/bonsai.splat",
            jobId: activeJobId || undefined,
        });
        closeSaveModal();
        await loadSplatsData();
        activeSplat = newSplat;
        updateActiveSceneHeader();
        openShareModal(newSplat);
    }
    catch (err) {
        alert(err instanceof Error ? err.message : "Failed to save splat");
    }
    finally {
        const submitBtn = document.getElementById("btn-submit-save-splat");
        submitBtn.disabled = false;
        submitBtn.textContent = "Save & Generate Link";
    }
});
// Save Angle / Camera config
btnSaveCamera.addEventListener("click", async () => {
    if (!activeSplat) {
        alert("Please save or select a database Splat first to store its camera viewpoint.");
        return;
    }
    try {
        btnSaveCamera.textContent = "Saving Angle...";
        await updateSplat(activeSplat.id, {
            cameraConfig: {
                position: [0, 1, 2],
                target: [0, 0, 0],
            },
        });
        btnSaveCamera.textContent = "Angle Saved!";
        setTimeout(() => {
            btnSaveCamera.innerHTML = `<span class="btn-icon">📐</span> Save Angle`;
        }, 2000);
    }
    catch (err) {
        alert(err instanceof Error ? err.message : "Failed to save angle");
        btnSaveCamera.innerHTML = `<span class="btn-icon">📐</span> Save Angle`;
    }
});
// ---------------- TAB NAVIGATION & FILTERS ----------------
tabSplats.addEventListener("click", () => {
    tabSplats.classList.add("active");
    tabTrain.classList.remove("active");
    paneSplats.style.display = "block";
    paneTrain.style.display = "none";
});
tabTrain.addEventListener("click", () => {
    tabTrain.classList.add("active");
    tabSplats.classList.remove("active");
    paneTrain.style.display = "block";
    paneSplats.style.display = "none";
});
filterPills.forEach((pill) => {
    pill.addEventListener("click", () => {
        filterPills.forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        activeFilter = pill.getAttribute("data-filter") || "all";
        renderSplatsList();
    });
});
// ---------------- SETTINGS MODAL ----------------
btnApiSettings.addEventListener("click", () => {
    settingsModal.style.display = "flex";
});
settingsModalClose.addEventListener("click", () => {
    settingsModal.style.display = "none";
});
settingsModal.addEventListener("click", (e) => {
    if (e.target === settingsModal)
        settingsModal.style.display = "none";
});
btnSaveSettings.addEventListener("click", () => {
    userApiKey = inputApiKey.value.trim();
    localStorage.setItem("pv_api_key", userApiKey);
    settingsModal.style.display = "none";
    alert("Settings saved!");
});
// ---------------- TRAINING & JOBS PIPELINE ----------------
function renderJobsList() {
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
            <div class="progress-bar-wrapper">
              <div class="progress-bar-fill" style="width: ${progressPct}%;"></div>
            </div>
            <span class="progress-text">${progressPct}%</span>
          </div>
          ${canTrain ? `<button class="btn btn-sm btn-accent btn-train-action" data-train-id="${job.id}">Start Training</button>` : ""}
        </div>
      `;
    })
        .join("");
    document.querySelectorAll(".job-card").forEach((card) => {
        card.addEventListener("click", (e) => {
            const target = e.target;
            if (target.classList.contains("btn-train-action"))
                return;
            selectJob(card.getAttribute("data-id"));
        });
    });
    document.querySelectorAll(".btn-train-action").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const jobId = btn.getAttribute("data-train-id");
            await handleTrain(jobId);
        });
    });
}
function updateLogsView(job) {
    logsConsole.textContent = job.logs || "No logs available.";
    logsConsole.scrollTop = logsConsole.scrollHeight;
}
async function selectJob(jobId) {
    activeJobId = jobId;
    activeSplat = null;
    btnTrain.style.display = "none";
    document.querySelectorAll(".job-card").forEach((card) => {
        card.classList.toggle("active", card.getAttribute("data-id") === jobId);
    });
    const job = currentJobs.find((j) => j.id === jobId);
    if (!job)
        return;
    updateActiveSceneHeader();
    updateLogsView(job);
    updateStepper(job);
    if (job.status === "PENDING" || job.status === "FAILED") {
        btnTrain.style.display = "inline-flex";
        btnTrain.onclick = () => handleTrain(jobId);
    }
    if (job.status === "COMPLETED" && job.splatPath) {
        currentLoadedPath = job.splatPath;
        const v = initViewer();
        await v.loadSplat(assetUrl(job.splatPath));
        if (job.collisionPath) {
            await v.loadCollisionMesh(assetUrl(job.collisionPath));
        }
    }
    else if (job.status === "FAILED") {
        viewerOverlayText.textContent = job.logs?.split("\n").filter((l) => l.includes("ERROR")).pop()?.replace(/^.*ERROR:\s*/, "") || "Training failed";
        viewerProgressIndicator.style.display = "none";
        viewerOverlay.style.display = "flex";
    }
    else if (job.status !== "COMPLETED") {
        const stage = job.status.replace("PROCESSING_", "");
        viewerOverlayText.textContent = `Training in progress — ${stage} (${job.progress.toFixed(0)}%)`;
        viewerProgressIndicator.style.display = "block";
        viewerProgressIndicator.value = job.progress;
        viewerOverlay.style.display = "flex";
    }
}
async function handleTrain(jobId) {
    try {
        btnTrain.disabled = true;
        btnTrain.textContent = "Starting...";
        await startTraining(jobId);
        await loadJobs();
        selectJob(jobId);
    }
    catch (e) {
        const msg = e instanceof Error ? e.message : "Training failed";
        alert(msg);
    }
    finally {
        btnTrain.disabled = false;
        btnTrain.textContent = "Start Training";
    }
}
// Upload handling
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("active"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("active"));
dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("active");
    if (e.dataTransfer?.files.length)
        uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
    if (fileInput.files?.length)
        uploadFile(fileInput.files[0]);
});
async function uploadFile(file) {
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
    }
    catch (e) {
        uploadProgressContainer.style.display = "none";
        const msg = e instanceof Error ? e.message : "Upload failed";
        alert(msg);
    }
}
btnLoadSample.addEventListener("click", async () => {
    const v = initViewer();
    activeSplat = null;
    activeJobId = null;
    currentLoadedPath = "/samples/bonsai.splat";
    updateActiveSceneHeader();
    stepper.update("PENDING", null);
    await v.loadSplat("/samples/bonsai.splat");
});
btnCapture.addEventListener("click", () => {
    viewer?.captureScreenshot(`splat-viewport-${activeSplat?.slug || activeJobId || "sample"}.png`);
});
// ---------------- INITIALIZATION & URL ROUTE HANDLING ----------------
async function checkUrlRouting() {
    const params = new URLSearchParams(window.location.search);
    const viewIdentifier = params.get("view") || params.get("splat") || params.get("s");
    const shareToken = params.get("token") || params.get("share");
    if (viewIdentifier) {
        try {
            viewerOverlayText.textContent = "Loading client showcase scene...";
            viewerOverlay.style.display = "flex";
            const splat = await getSplat(viewIdentifier, shareToken || undefined, userApiKey || undefined);
            if (splat) {
                activeSplat = splat;
                currentLoadedPath = splat.splatPath;
                updateActiveSceneHeader();
                // Enable presentation mode directly for client view
                setClientMode(true);
                const v = initViewer();
                await v.loadSplat(assetUrl(splat.splatPath));
                return true;
            }
        }
        catch (err) {
            console.error("URL showcase load error:", err);
            viewerOverlayText.textContent = err instanceof Error ? err.message : "Could not load shared scene";
            viewerProgressIndicator.style.display = "none";
            return false;
        }
    }
    return false;
}
async function init() {
    const isOnline = await updateBackendStatus();
    if (isOnline) {
        await loadSplatsData();
        await loadJobs();
    }
    const isSharedView = await checkUrlRouting();
    if (!isSharedView) {
        // If no specific route in URL, load sample by default
        const v = initViewer();
        if (currentSplats.length > 0) {
            selectSplatById(currentSplats[0].id);
        }
        else {
            v.loadSplat("/samples/bonsai.splat");
        }
    }
    // Periodic polling for backend jobs / splats updates
    setInterval(async () => {
        if (await updateBackendStatus()) {
            if (!isClientMode) {
                await loadJobs();
            }
            if (activeJobId) {
                const job = currentJobs.find((j) => j.id === activeJobId);
                if (job?.status === "COMPLETED" && job.splatPath) {
                    const overlayVisible = viewerOverlay.style.display !== "none";
                    if (overlayVisible)
                        selectJob(activeJobId);
                }
            }
        }
    }, 3000);
}
init();
