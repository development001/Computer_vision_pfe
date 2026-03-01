const state = {
  datasets: [],
  selectedDatasetId: null,
  versions: [],
  activeJobId: null,
  logOffset: 0,
  jobPollTimer: null,
  trainingApiUnavailable: false,
};

const t = window.TrainingShared;

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  initialize();
});

function bindEvents() {
  document.getElementById("train-dataset").addEventListener("change", onDatasetChange);
  document.getElementById("start-training-btn").addEventListener("click", startTraining);
  document.getElementById("stop-training-btn").addEventListener("click", stopTraining);
}

async function initialize() {
  try {
    state.datasets = await t.fetchDatasets();
    state.selectedDatasetId = t.resolveDatasetId(state.datasets, t.getStoredDatasetId());
    t.setStoredDatasetId(state.selectedDatasetId);
    renderDatasetSelect();
    await fetchVersions();
    await fetchModelSources();
    await pollJobs();
    state.jobPollTimer = setInterval(pollJobs, 5000);
  } catch (e) {
    t.notify(e.message);
  }
}

function renderDatasetSelect() {
  const select = document.getElementById("train-dataset");
  t.populateDatasetSelect(select, state.datasets, state.selectedDatasetId, "No datasets available");
}

async function onDatasetChange() {
  state.selectedDatasetId = document.getElementById("train-dataset").value || null;
  t.setStoredDatasetId(state.selectedDatasetId);
  await fetchVersions();
}

async function fetchVersions() {
  const select = document.getElementById("train-version");
  select.innerHTML = "";
  state.versions = [];
  if (!state.selectedDatasetId) return;

  try {
    const data = await t.api(`/training/datasets/${state.selectedDatasetId}/annotation-versions`);
    state.versions = data.annotation_versions || [];
    state.versions.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = v.name;
      select.appendChild(opt);
    });
  } catch (e) {
    t.notify(e.message);
  }
}

async function fetchModelSources() {
  const preset = ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"];
  const select = document.getElementById("train-model");
  select.innerHTML = "";
  try {
    const data = await t.api("/models");
    const uploaded = (data.models || []).filter((m) => m.endsWith(".pt"));
    [...preset, ...uploaded].forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      select.appendChild(opt);
    });
  } catch (e) {
    console.error(e);
  }
}

async function startTraining() {
  if (!state.selectedDatasetId) return t.notify("select a dataset first");
  const annotation_version_id = document.getElementById("train-version").value;
  if (!annotation_version_id) return t.notify("select annotation version");

  const payload = {
    dataset_id: state.selectedDatasetId,
    annotation_version_id,
    model_source: document.getElementById("train-model").value,
    epochs: parseInt(document.getElementById("train-epochs").value, 10) || 50,
    batch_size: parseInt(document.getElementById("train-batch").value, 10) || 16,
    imgsz: parseInt(document.getElementById("train-imgsz").value, 10) || 640,
    split_train: parseFloat(document.getElementById("split-train").value) || 0.8,
    split_val: parseFloat(document.getElementById("split-val").value) || 0.1,
    split_test: parseFloat(document.getElementById("split-test").value) || 0.1,
    seed: 42,
  };

  try {
    const job = await t.api("/training/jobs/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.activeJobId = job.id;
    state.logOffset = 0;
    document.getElementById("training-logs").textContent = "";
    t.notify("training started");
  } catch (e) {
    t.notify(e.message);
  }
}

async function stopTraining() {
  if (!state.activeJobId) return t.notify("no active training job");
  try {
    await t.api(`/training/jobs/${state.activeJobId}/stop`, { method: "POST" });
    t.notify("stop requested");
  } catch (e) {
    t.notify(e.message);
  }
}

async function pollJobs() {
  if (state.trainingApiUnavailable) return;

  try {
    const data = await t.api("/training/jobs");
    state.activeJobId = data.active_job_id || null;
    let active = null;
    if (state.activeJobId) {
      active = data.jobs.find((j) => j.id === state.activeJobId) || null;
    } else if ((data.jobs || []).length > 0) {
      active = data.jobs[0];
    }

    renderJobStatus(active);
    if (active) {
      await pollLogs(active.id);
      if (active.status !== "running" && active.status !== "starting") {
        state.activeJobId = null;
      }
    }
  } catch (e) {
    const msg = e && e.message ? e.message : "";
    if (msg.includes("404")) {
      state.trainingApiUnavailable = true;
      if (state.jobPollTimer) {
        clearInterval(state.jobPollTimer);
        state.jobPollTimer = null;
      }
      document.getElementById("training-status").textContent = "Training API unavailable (404). Restart backend to enable training features.";
      return;
    }
    console.error(e);
  }
}

function renderJobStatus(job) {
  const el = document.getElementById("training-status");
  if (!job) {
    el.textContent = "No training jobs yet.";
    return;
  }

  el.textContent = `Job ${job.id.slice(0, 8)} | ${job.status} | Epoch ${job.epoch_current}/${job.epoch_total} | ${(
    job.progress_pct || 0
  ).toFixed(1)}%`;
}

async function pollLogs(jobId) {
  const data = await t.api(`/training/jobs/${jobId}/logs?offset=${state.logOffset}`);
  const logsEl = document.getElementById("training-logs");
  if (data.chunk) {
    logsEl.textContent += data.chunk;
    logsEl.scrollTop = logsEl.scrollHeight;
  }
  state.logOffset = data.next_offset || state.logOffset;
}
