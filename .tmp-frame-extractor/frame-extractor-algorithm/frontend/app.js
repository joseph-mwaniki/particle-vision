const videoInput = document.getElementById('video-input');
const uploadButton = document.getElementById('upload-button');
const analyzeButton = document.getElementById('analyze-button');
const videoMeta = document.getElementById('video-meta');
const uploadList = document.getElementById('upload-list');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const reviewGrid = document.getElementById('review-grid');
const warningsBox = document.getElementById('warnings');
const jobStatusBanner = document.getElementById('job-status-banner');
const showSelectedButton = document.getElementById('show-selected');
const showRejectedButton = document.getElementById('show-rejected');

const state = {
  jobs: [],
  activeJobId: null,
  isUploading: false,
  isAnalyzing: false,
  currentView: 'selected',
  selectedFrames: [],
  rejectedFrames: [],
  warnings: [],
  pageSize: 24,
  reviewKey: null,
  renderedFrameKeys: new Set(),
  currentPage: {
    selected: 1,
    rejected: 1,
  },
};

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function setProgress(progress, message) {
  const safeProgress = Math.max(0, Math.min(100, Number(progress) || 0));
  const progressBar = progressFill.parentElement;
  progressFill.style.width = `${safeProgress}%`;
  progressBar.setAttribute('aria-valuenow', String(safeProgress));
  progressBar.setAttribute('aria-valuetext', message);
  progressText.textContent = message;
}

function renderStats(stats) {
  document.getElementById('stat-analyzed').textContent = formatNumber(stats.analyzed_frames || 0);
  document.getElementById('stat-blurry').textContent = formatNumber(stats.blurry_frames || 0);
  document.getElementById('stat-exposure').textContent = formatNumber(stats.exposure_rejected || 0);
  document.getElementById('stat-redundant').textContent = formatNumber(stats.redundant_frames || 0);
  document.getElementById('stat-selected').textContent = formatNumber(stats.selected_frames || 0);
}

function renderWarnings(warnings) {
  warningsBox.innerHTML = '';
  if (!warnings.length) {
    return;
  }
  warnings.forEach((warning) => {
    const line = document.createElement('div');
    line.className = 'warning';
    line.textContent = warning;
    warningsBox.appendChild(line);
  });
}

function renderJobStatus(job) {
  const label = job && job.status ? job.status.toUpperCase() : 'WAITING';
  const message = job && job.message ? job.message : 'Waiting for upload';
  const warningText = Array.isArray(job && job.warnings) && job.warnings.length ? ' — warnings present' : '';
  jobStatusBanner.textContent = `${label}${warningText}: ${message}`;
  jobStatusBanner.style.background = warningText ? 'rgba(255, 223, 138, 0.08)' : 'rgba(103, 217, 232, 0.08)';
  jobStatusBanner.style.borderColor = warningText ? 'rgba(255, 223, 138, 0.45)' : 'rgba(103, 217, 232, 0.3)';
}

function renderQueue() {
  uploadList.innerHTML = '';
  const completedJobs = state.jobs.filter((job) => job.status === 'completed');
  if (completedJobs.length) {
    const combinedButton = document.createElement('button');
    combinedButton.type = 'button';
    combinedButton.className = `upload-item${state.activeJobId === 'combined' ? ' active' : ''}`;
    combinedButton.setAttribute('aria-pressed', String(state.activeJobId === 'combined'));

    const combinedName = document.createElement('span');
    combinedName.className = 'upload-item-name';
    combinedName.textContent = `Combined results (${completedJobs.length} videos)`;

    const combinedStatus = document.createElement('span');
    combinedStatus.className = 'upload-item-status';
    combinedStatus.textContent = 'completed';

    combinedButton.append(combinedName, combinedStatus);
    combinedButton.addEventListener('click', selectCombined);
    uploadList.appendChild(combinedButton);
  }

  state.jobs.forEach((job) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `upload-item${job.job_id === state.activeJobId ? ' active' : ''}`;
    button.setAttribute('aria-pressed', String(job.job_id === state.activeJobId));

    const name = document.createElement('span');
    name.className = 'upload-item-name';
    name.textContent = job.filename;

    const status = document.createElement('span');
    status.className = 'upload-item-status';
    status.textContent = job.status;

    button.append(name, status);
    button.addEventListener('click', () => selectJob(job.job_id));
    uploadList.appendChild(button);
  });

  const pendingCount = state.jobs.filter((job) => job.status === 'uploaded' || job.status === 'failed').length;
  analyzeButton.disabled = state.isUploading || state.isAnalyzing || pendingCount === 0;
  analyzeButton.classList.toggle('disabled', analyzeButton.disabled);
  analyzeButton.textContent = pendingCount ? `Analyze Videos (${pendingCount})` : 'Analyze Videos';
  uploadButton.disabled = state.isUploading || state.isAnalyzing;
}

function selectJob(jobId) {
  const job = state.jobs.find((item) => item.job_id === jobId);
  if (!job) return;

  state.activeJobId = jobId;
  state.selectedFrames = job.selected_frames || [];
  state.rejectedFrames = job.rejected_preview || [];
  document.getElementById('video-name').textContent = job.filename;
  videoMeta.classList.remove('hidden');
  renderStats(job.stats || {});
  renderWarnings(job.warnings || []);
  renderJobStatus(job);
  setProgress(job.progress || 0, job.message || job.status);
  renderQueue();
  renderReview();
}

function selectCombined() {
  const completedJobs = state.jobs.filter((job) => job.status === 'completed');
  if (!completedJobs.length) return;

  state.activeJobId = 'combined';
  state.selectedFrames = completedJobs.flatMap((job) => job.selected_frames || []);
  state.rejectedFrames = completedJobs.flatMap((job) => job.rejected_preview || []);
  const stats = ['analyzed_frames', 'blurry_frames', 'exposure_rejected', 'redundant_frames', 'selected_frames']
    .reduce((combined, key) => {
      combined[key] = completedJobs.reduce((total, job) => total + Number(job.stats?.[key] || 0), 0);
      return combined;
    }, {});
  document.getElementById('video-name').textContent = `Combined results (${completedJobs.length} videos)`;
  videoMeta.classList.remove('hidden');
  renderStats(stats);
  renderWarnings([...new Set(completedJobs.flatMap((job) => job.warnings || []))]);
  jobStatusBanner.textContent = `COMPLETED: Combined results from ${completedJobs.length} videos`;
  jobStatusBanner.style.background = 'rgba(103, 217, 232, 0.08)';
  jobStatusBanner.style.borderColor = 'rgba(103, 217, 232, 0.3)';
  setProgress(100, `${completedJobs.length} videos combined`);
  renderQueue();
  renderReview();
}

async function uploadVideos(files) {
  if (!files.length) return;

  state.isUploading = true;
  renderQueue();
  setProgress(0, `Uploading ${files.length} video${files.length === 1 ? '' : 's'}`);
  const uploadErrors = [];
  try {
    for (const [index, file] of files.entries()) {
      try {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Upload failed');

        state.jobs.push({
          job_id: data.job_id,
          filename: file.name,
          status: 'uploaded',
          progress: 0,
          message: 'Uploaded and ready to analyze',
          selected_frames: [],
          rejected_preview: [],
          stats: {},
          warnings: [],
        });
        state.activeJobId = data.job_id;
      } catch (error) {
        uploadErrors.push(`${file.name}: ${error.message}`);
      }
      setProgress(Math.round(((index + 1) / files.length) * 100), `Uploaded ${index + 1} of ${files.length} videos`);
    }
  } finally {
    state.isUploading = false;
    if (state.activeJobId) selectJob(state.activeJobId);
    renderQueue();
  }
  if (uploadErrors.length) alert(uploadErrors.join('\n'));
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function pollJob(queueJob) {
  while (true) {
    const response = await fetch(`/api/jobs/${queueJob.job_id}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || 'Job lookup failed');

    Object.assign(queueJob, job);
    renderQueue();
    if (queueJob.job_id === state.activeJobId) selectJob(queueJob.job_id);
    if (job.status === 'completed' || job.status === 'failed') return;
    await wait(1200);
  }
}

async function analyzeVideos() {
  state.isAnalyzing = true;
  renderQueue();
  try {
    for (const job of state.jobs) {
      if (job.status !== 'uploaded' && job.status !== 'failed') continue;
      state.activeJobId = job.job_id;
      selectJob(job.job_id);
      try {
        const response = await fetch(`/api/analyze/${job.job_id}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Analysis request failed');
        await pollJob(job);
      } catch (error) {
        job.status = 'failed';
        job.message = error.message;
        job.warnings = [error.message];
        selectJob(job.job_id);
      }
    }
    selectCombined();
  } finally {
    state.isAnalyzing = false;
    renderQueue();
  }
}

function renderReview() {
  const frames = state.currentView === 'selected' ? state.selectedFrames : state.rejectedFrames;
  const reviewKey = `${state.activeJobId}:${state.currentView}:${state.currentPage[state.currentView] || 1}`;
  if (state.reviewKey !== reviewKey) {
    reviewGrid.innerHTML = '';
    state.reviewKey = reviewKey;
    state.renderedFrameKeys = new Set();
  }

  if (!frames.length) {
    if (!reviewGrid.querySelector('.empty-state')) {
      reviewGrid.innerHTML = '<div class="empty-state">No frames available yet.</div>';
    }
    return;
  }
  reviewGrid.querySelector('.empty-state')?.remove();

  const page = state.currentPage[state.currentView] || 1;
  const pageCount = Math.max(1, Math.ceil(frames.length / state.pageSize));
  const safePage = Math.min(page, pageCount);
  state.currentPage[state.currentView] = safePage;

  const startIndex = (safePage - 1) * state.pageSize;
  const endIndex = Math.min(startIndex + state.pageSize, frames.length);
  const visibleFrames = frames.slice(startIndex, endIndex);

  const summary = document.createElement('div');
  summary.className = 'review-summary';
  summary.textContent = `Showing ${startIndex + 1}-${endIndex} of ${frames.length}`;
  const existingSummary = reviewGrid.querySelector('.review-summary');
  if (existingSummary) {
    existingSummary.textContent = summary.textContent;
  } else {
    reviewGrid.appendChild(summary);
  }

  const pager = document.createElement('div');
  pager.className = 'review-pager';

  const prevButton = document.createElement('button');
  prevButton.type = 'button';
  prevButton.textContent = 'Previous';
  prevButton.disabled = safePage <= 1;
  prevButton.addEventListener('click', () => {
    if (safePage > 1) {
      state.currentPage[state.currentView] = safePage - 1;
      renderReview();
    }
  });

  const pageInfo = document.createElement('span');
  pageInfo.textContent = `Page ${safePage}/${pageCount}`;

  const nextButton = document.createElement('button');
  nextButton.type = 'button';
  nextButton.textContent = 'Next';
  nextButton.disabled = safePage >= pageCount;
  nextButton.addEventListener('click', () => {
    if (safePage < pageCount) {
      state.currentPage[state.currentView] = safePage + 1;
      renderReview();
    }
  });

  pager.append(prevButton, pageInfo, nextButton);
  reviewGrid.querySelector('.review-pager')?.remove();
  reviewGrid.insertBefore(pager, reviewGrid.querySelector('.review-summary').nextSibling);

  visibleFrames.forEach((frame) => {
    const frameKey = `${frame.job_id || state.activeJobId}:${frame.output_file}`;
    if (state.renderedFrameKeys.has(frameKey)) return;
    const card = document.createElement('article');
    card.className = 'frame-card';
    card.dataset.frameKey = frameKey;

    const img = document.createElement('img');
    const folder = state.currentView === 'selected' ? 'selected_frames' : 'rejected_frames';
    img.src = `/output/${folder}/${frame.output_file}`;
    img.alt = `Frame at ${frame.timestamp}s`;
    img.loading = 'lazy';

    const details = document.createElement('div');
    details.className = 'frame-details';
    details.innerHTML = `
      <strong>Frame: ${frame.original_frame}</strong>
      <span>Video: ${frame.source_video || 'Unknown'}</span>
      <span>Time: ${Number(frame.timestamp).toFixed(2)}s</span>
      <span>Status: ${String(frame.status || 'UNKNOWN').toUpperCase()}</span>
      <span>Reason: ${frame.reason || 'N/A'}</span>
    `;

    card.appendChild(img);
    card.appendChild(details);
    reviewGrid.appendChild(card);
    state.renderedFrameKeys.add(frameKey);
  });
}

uploadButton.addEventListener('click', () => {
  videoInput.click();
});

videoInput.addEventListener('change', (event) => {
  uploadVideos(Array.from(event.target.files || []));
  videoInput.value = '';
});

analyzeButton.addEventListener('click', analyzeVideos);
showSelectedButton.addEventListener('click', () => {
  state.currentView = 'selected';
  showSelectedButton.classList.add('active');
  showRejectedButton.classList.remove('active');
  renderReview();
});
showRejectedButton.addEventListener('click', () => {
  state.currentView = 'rejected';
  showRejectedButton.classList.add('active');
  showSelectedButton.classList.remove('active');
  renderReview();
});

setProgress(0, 'Waiting for upload');
renderReview();
