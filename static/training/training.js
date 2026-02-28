const state = {
  datasets: [],
  selectedDatasetId: null,
  selectedVersionId: null,
  images: [],
  classes: [],
  versions: [],
  selectedImageId: null,
  annotations: [],
  selectedBoxIndex: -1,
  imageObj: null,
  canvasScale: 1,
  jobPollTimer: null,
  logOffset: 0,
  activeJobId: null,
  trainingApiUnavailable: false,
};

const canvas = document.getElementById("annotator-canvas");
const ctx = canvas.getContext("2d");
let drawMode = null;
let dragStart = null;
let dragOffset = null;

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  fetchDatasets();
  fetchModelSources();
  pollJobs();
  state.jobPollTimer = setInterval(pollJobs, 5000);
});

function bindEvents() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });

  document.getElementById("create-dataset-btn").addEventListener("click", createDataset);
  document.getElementById("upload-images-btn").addEventListener("click", uploadImages);
  document.getElementById("add-class-btn").addEventListener("click", addClass);
  document.getElementById("create-version-btn").addEventListener("click", createVersion);
  document.getElementById("annotator-image").addEventListener("change", onAnnotatorImageChange);
  document.getElementById("save-annotations-btn").addEventListener("click", saveAnnotations);
  document.getElementById("delete-box-btn").addEventListener("click", deleteSelectedBox);
  document.getElementById("start-training-btn").addEventListener("click", startTraining);
  document.getElementById("stop-training-btn").addEventListener("click", stopTraining);

  canvas.addEventListener("mousedown", onCanvasDown);
  canvas.addEventListener("mousemove", onCanvasMove);
  canvas.addEventListener("mouseup", onCanvasUp);
}

function notify(message) {
  alert(message);
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `request failed: ${res.status}`);
  }
  return data;
}

async function fetchDatasets() {
  try {
    const data = await api("/training/datasets");
    state.datasets = data.datasets || [];
    renderDatasets();
  } catch (e) {
    notify(e.message);
  }
}

function renderDatasets() {
  const el = document.getElementById("datasets-list");
  el.innerHTML = "";
  state.datasets.forEach((d) => {
    const row = document.createElement("div");
    row.className = `list-item ${state.selectedDatasetId === d.id ? "active" : ""}`;
    row.innerHTML = `
      <div>
        <strong>${d.name}</strong><br/>
        <small>${d.image_count} images, ${d.class_count} classes, ${d.annotation_version_count} versions</small>
      </div>
      <div class="item-actions">
        <button class="btn btn-secondary">Open</button>
        <button class="btn btn-secondary">Delete</button>
      </div>
    `;
    const btns = row.querySelectorAll("button");
    btns[0].onclick = () => selectDataset(d.id);
    btns[1].onclick = () => deleteDataset(d.id);
    el.appendChild(row);
  });
}

async function createDataset() {
  const name = document.getElementById("dataset-name").value.trim();
  const description = document.getElementById("dataset-description").value.trim();
  if (!name) return notify("dataset name is required");
  try {
    const d = await api("/training/datasets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    state.selectedDatasetId = d.id;
    document.getElementById("dataset-name").value = "";
    document.getElementById("dataset-description").value = "";
    await fetchDatasets();
    await selectDataset(d.id);
  } catch (e) {
    notify(e.message);
  }
}

async function deleteDataset(datasetId) {
  if (!confirm("Delete this dataset and all related files?")) return;
  try {
    await api(`/training/datasets/${datasetId}`, { method: "DELETE" });
    if (state.selectedDatasetId === datasetId) {
      state.selectedDatasetId = null;
      resetDetails();
    }
    await fetchDatasets();
  } catch (e) {
    notify(e.message);
  }
}

function resetDetails() {
  state.images = [];
  state.classes = [];
  state.versions = [];
  state.selectedVersionId = null;
  state.selectedImageId = null;
  state.annotations = [];
  state.imageObj = null;
  document.getElementById("dataset-selected-info").textContent = "Select a dataset to manage its data.";
  document.getElementById("images-list").innerHTML = "";
  document.getElementById("classes-list").innerHTML = "";
  document.getElementById("versions-list").innerHTML = "";
  document.getElementById("annotator-image").innerHTML = "";
  document.getElementById("annotator-class").innerHTML = "";
  document.getElementById("train-version").innerHTML = "";
  drawCanvas();
}

async function selectDataset(datasetId) {
  state.selectedDatasetId = datasetId;
  state.selectedVersionId = null;
  state.selectedImageId = null;
  renderDatasets();
  const d = state.datasets.find((x) => x.id === datasetId);
  document.getElementById("dataset-selected-info").textContent = `${d.name} - ${d.description || "No description"}`;
  await Promise.all([fetchImages(), fetchClasses(), fetchVersions()]);
  await refreshAnnotatorData();
}

async function fetchImages() {
  if (!state.selectedDatasetId) return;
  const data = await api(`/training/datasets/${state.selectedDatasetId}/images`);
  state.images = data.images || [];
  renderImages();
}

function renderImages() {
  const list = document.getElementById("images-list");
  const select = document.getElementById("annotator-image");
  list.innerHTML = "";
  select.innerHTML = "";
  state.images.forEach((img) => {
    const row = document.createElement("div");
    row.className = "list-item";
    row.innerHTML = `
      <div>${img.original_name}</div>
      <div class="item-actions">
        <button class="btn btn-secondary">Delete</button>
      </div>
    `;
    row.querySelector("button").onclick = () => deleteImage(img.id);
    list.appendChild(row);
    const opt = document.createElement("option");
    opt.value = img.id;
    opt.textContent = img.original_name;
    select.appendChild(opt);
  });
  if (!state.selectedImageId && state.images.length > 0) {
    state.selectedImageId = state.images[0].id;
  }
  if (state.selectedImageId && !state.images.find((x) => x.id === state.selectedImageId)) {
    state.selectedImageId = state.images.length > 0 ? state.images[0].id : null;
  }
  if (state.selectedImageId) {
    select.value = state.selectedImageId;
  }
}

async function uploadImages() {
  if (!state.selectedDatasetId) return notify("select a dataset first");
  const input = document.getElementById("image-upload");
  if (!input.files || input.files.length === 0) return notify("select images first");
  const form = new FormData();
  for (const f of input.files) form.append("files", f);
  try {
    await api(`/training/datasets/${state.selectedDatasetId}/images`, { method: "POST", body: form });
    input.value = "";
    await fetchImages();
    await refreshAnnotatorData();
  } catch (e) {
    notify(e.message);
  }
}

async function deleteImage(imageId) {
  if (!state.selectedDatasetId) return;
  if (!confirm("Delete this image and all its labels?")) return;
  try {
    await api(`/training/datasets/${state.selectedDatasetId}/images/${imageId}`, { method: "DELETE" });
    if (state.selectedImageId === imageId) state.selectedImageId = null;
    await fetchImages();
    await refreshAnnotatorData();
  } catch (e) {
    notify(e.message);
  }
}

async function fetchClasses() {
  if (!state.selectedDatasetId) return;
  const data = await api(`/training/datasets/${state.selectedDatasetId}/classes`);
  state.classes = data.classes || [];
  renderClasses();
}

function renderClasses() {
  const list = document.getElementById("classes-list");
  const select = document.getElementById("annotator-class");
  list.innerHTML = "";
  select.innerHTML = "";
  state.classes.forEach((c) => {
    const row = document.createElement("div");
    row.className = "list-item";
    row.innerHTML = `
      <div>
        <span style="display:inline-block;width:12px;height:12px;background:${c.color};border-radius:50%;margin-right:8px;"></span>
        ${c.id}: ${c.name}
      </div>
      <div class="item-actions">
        <button class="btn btn-secondary">Edit</button>
        <button class="btn btn-secondary">Delete</button>
      </div>
    `;
    const buttons = row.querySelectorAll("button");
    buttons[0].onclick = () => editClass(c);
    buttons[1].onclick = () => removeClass(c.id);
    list.appendChild(row);

    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = `${c.id}: ${c.name}`;
    select.appendChild(opt);
  });
}

async function addClass() {
  if (!state.selectedDatasetId) return notify("select a dataset first");
  const name = document.getElementById("class-name").value.trim();
  const color = document.getElementById("class-color").value;
  if (!name) return notify("class name is required");
  try {
    await api(`/training/datasets/${state.selectedDatasetId}/classes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, color }),
    });
    document.getElementById("class-name").value = "";
    await fetchClasses();
  } catch (e) {
    notify(e.message);
  }
}

async function editClass(c) {
  const name = prompt("New class name:", c.name);
  if (name === null) return;
  const color = prompt("New color (hex):", c.color);
  if (color === null) return;
  try {
    await api(`/training/datasets/${state.selectedDatasetId}/classes/${c.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, color }),
    });
    await fetchClasses();
  } catch (e) {
    notify(e.message);
  }
}

async function removeClass(classId) {
  if (!confirm("Delete this class? This is blocked if used in annotations.")) return;
  try {
    await api(`/training/datasets/${state.selectedDatasetId}/classes/${classId}`, { method: "DELETE" });
    await fetchClasses();
  } catch (e) {
    notify(e.message);
  }
}

async function fetchVersions() {
  if (!state.selectedDatasetId) return;
  const data = await api(`/training/datasets/${state.selectedDatasetId}/annotation-versions`);
  state.versions = data.annotation_versions || [];
  renderVersions();
}

function renderVersions() {
  const list = document.getElementById("versions-list");
  const sourceSelect = document.getElementById("source-version");
  const annotatorVersion = document.getElementById("train-version");
  list.innerHTML = "";
  sourceSelect.innerHTML = `<option value="">Empty version</option>`;
  annotatorVersion.innerHTML = "";

  state.versions.forEach((v) => {
    const row = document.createElement("div");
    row.className = `list-item ${state.selectedVersionId === v.id ? "active" : ""}`;
    row.innerHTML = `
      <div>${v.name}</div>
      <div class="item-actions">
        <button class="btn btn-secondary">Use</button>
        <button class="btn btn-secondary">Rename</button>
        <button class="btn btn-secondary">Delete</button>
      </div>
    `;
    const [useBtn, renameBtn, deleteBtn] = row.querySelectorAll("button");
    useBtn.onclick = async () => {
      state.selectedVersionId = v.id;
      renderVersions();
      await refreshAnnotatorData();
    };
    renameBtn.onclick = () => renameVersion(v);
    deleteBtn.onclick = () => deleteVersion(v.id);
    list.appendChild(row);

    const s1 = document.createElement("option");
    s1.value = v.id;
    s1.textContent = v.name;
    sourceSelect.appendChild(s1);

    const s2 = document.createElement("option");
    s2.value = v.id;
    s2.textContent = v.name;
    annotatorVersion.appendChild(s2);
  });

  if (!state.selectedVersionId && state.versions.length > 0) {
    state.selectedVersionId = state.versions[0].id;
  }
  if (state.selectedVersionId) {
    annotatorVersion.value = state.selectedVersionId;
  }
}

async function createVersion() {
  if (!state.selectedDatasetId) return notify("select a dataset first");
  const name = document.getElementById("version-name").value.trim();
  const sourceVersionId = document.getElementById("source-version").value || null;
  if (!name) return notify("version name is required");
  try {
    const v = await api(`/training/datasets/${state.selectedDatasetId}/annotation-versions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, source_version_id: sourceVersionId }),
    });
    state.selectedVersionId = v.id;
    document.getElementById("version-name").value = "";
    await fetchVersions();
    await refreshAnnotatorData();
  } catch (e) {
    notify(e.message);
  }
}

async function renameVersion(v) {
  const name = prompt("New version name:", v.name);
  if (name === null) return;
  try {
    await api(`/training/datasets/${state.selectedDatasetId}/annotation-versions/${v.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    await fetchVersions();
  } catch (e) {
    notify(e.message);
  }
}

async function deleteVersion(versionId) {
  if (!confirm("Delete this annotation version?")) return;
  try {
    await api(`/training/datasets/${state.selectedDatasetId}/annotation-versions/${versionId}`, { method: "DELETE" });
    if (state.selectedVersionId === versionId) state.selectedVersionId = null;
    await fetchVersions();
    await refreshAnnotatorData();
  } catch (e) {
    notify(e.message);
  }
}

async function refreshAnnotatorData() {
  if (!state.selectedDatasetId || !state.selectedVersionId || !state.selectedImageId) {
    state.annotations = [];
    state.selectedBoxIndex = -1;
    drawCanvas();
    return;
  }
  await loadImage();
  await loadAnnotations();
  drawCanvas();
}

async function onAnnotatorImageChange() {
  state.selectedImageId = document.getElementById("annotator-image").value || null;
  await refreshAnnotatorData();
}

async function loadImage() {
  const image = state.images.find((x) => x.id === state.selectedImageId);
  if (!image) {
    state.imageObj = null;
    return;
  }
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = reject;
    img.src = image.url;
  });
  state.imageObj = img;
  const maxWidth = 900;
  const scale = img.width > maxWidth ? maxWidth / img.width : 1;
  state.canvasScale = scale;
  canvas.width = Math.round(img.width * scale);
  canvas.height = Math.round(img.height * scale);
}

async function loadAnnotations() {
  const data = await api(
    `/training/datasets/${state.selectedDatasetId}/annotation-versions/${state.selectedVersionId}/annotations/${state.selectedImageId}`
  );
  state.annotations = data.annotations || [];
  state.selectedBoxIndex = -1;
}

function toCanvasBox(a) {
  if (!state.imageObj) return null;
  const iw = state.imageObj.width;
  const ih = state.imageObj.height;
  const x = (a.x - a.w / 2) * iw * state.canvasScale;
  const y = (a.y - a.h / 2) * ih * state.canvasScale;
  const w = a.w * iw * state.canvasScale;
  const h = a.h * ih * state.canvasScale;
  return { x, y, w, h };
}

function toYoloBox(box) {
  const iw = state.imageObj.width;
  const ih = state.imageObj.height;
  const x = (box.x + box.w / 2) / (iw * state.canvasScale);
  const y = (box.y + box.h / 2) / (ih * state.canvasScale);
  const w = box.w / (iw * state.canvasScale);
  const h = box.h / (ih * state.canvasScale);
  return {
    class_id: parseInt(document.getElementById("annotator-class").value, 10),
    x: clamp01(x),
    y: clamp01(y),
    w: clamp01(w),
    h: clamp01(h),
  };
}

function clamp01(v) {
  return Math.min(1, Math.max(0, v));
}

function drawCanvas(tempBox = null) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!state.imageObj) {
    ctx.fillStyle = "#1f2937";
    ctx.fillRect(0, 0, canvas.width || 600, canvas.height || 300);
    return;
  }
  ctx.drawImage(state.imageObj, 0, 0, canvas.width, canvas.height);

  state.annotations.forEach((a, idx) => {
    const b = toCanvasBox(a);
    const cls = state.classes.find((c) => c.id === a.class_id);
    const color = cls ? cls.color : "#00ff00";
    ctx.strokeStyle = idx === state.selectedBoxIndex ? "#ffffff" : color;
    ctx.lineWidth = idx === state.selectedBoxIndex ? 3 : 2;
    ctx.strokeRect(b.x, b.y, b.w, b.h);
    ctx.fillStyle = color;
    ctx.font = "12px Inter";
    ctx.fillText(cls ? cls.name : String(a.class_id), b.x + 2, Math.max(12, b.y - 4));
  });

  if (tempBox) {
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 2;
    ctx.strokeRect(tempBox.x, tempBox.y, tempBox.w, tempBox.h);
  }
}

function findHitBox(x, y) {
  for (let i = state.annotations.length - 1; i >= 0; i--) {
    const b = toCanvasBox(state.annotations[i]);
    if (x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) {
      return i;
    }
  }
  return -1;
}

function onCanvasDown(ev) {
  if (!state.imageObj || !state.selectedVersionId) return;
  const rect = canvas.getBoundingClientRect();
  const x = ev.clientX - rect.left;
  const y = ev.clientY - rect.top;
  const hit = findHitBox(x, y);
  if (hit >= 0) {
    state.selectedBoxIndex = hit;
    drawMode = "move";
    const b = toCanvasBox(state.annotations[hit]);
    dragOffset = { x: x - b.x, y: y - b.y, w: b.w, h: b.h };
  } else {
    state.selectedBoxIndex = -1;
    drawMode = "draw";
    dragStart = { x, y };
  }
  drawCanvas();
}

function onCanvasMove(ev) {
  if (!drawMode) return;
  const rect = canvas.getBoundingClientRect();
  const x = ev.clientX - rect.left;
  const y = ev.clientY - rect.top;

  if (drawMode === "draw") {
    const box = {
      x: Math.min(dragStart.x, x),
      y: Math.min(dragStart.y, y),
      w: Math.abs(x - dragStart.x),
      h: Math.abs(y - dragStart.y),
    };
    drawCanvas(box);
    return;
  }

  if (drawMode === "move" && state.selectedBoxIndex >= 0) {
    const nx = x - dragOffset.x;
    const ny = y - dragOffset.y;
    const box = { x: nx, y: ny, w: dragOffset.w, h: dragOffset.h };
    const class_id = state.annotations[state.selectedBoxIndex].class_id;
    state.annotations[state.selectedBoxIndex] = { ...toYoloBox(box), class_id };
    drawCanvas();
  }
}

function onCanvasUp(ev) {
  if (!drawMode) return;
  const rect = canvas.getBoundingClientRect();
  const x = ev.clientX - rect.left;
  const y = ev.clientY - rect.top;

  if (drawMode === "draw") {
    const box = {
      x: Math.min(dragStart.x, x),
      y: Math.min(dragStart.y, y),
      w: Math.abs(x - dragStart.x),
      h: Math.abs(y - dragStart.y),
    };
    if (box.w > 4 && box.h > 4) {
      state.annotations.push(toYoloBox(box));
      state.selectedBoxIndex = state.annotations.length - 1;
    }
  }
  drawMode = null;
  dragStart = null;
  dragOffset = null;
  drawCanvas();
}

function deleteSelectedBox() {
  if (state.selectedBoxIndex < 0) return;
  state.annotations.splice(state.selectedBoxIndex, 1);
  state.selectedBoxIndex = -1;
  drawCanvas();
}

async function saveAnnotations() {
  if (!state.selectedDatasetId || !state.selectedVersionId || !state.selectedImageId) {
    return notify("select dataset, version and image first");
  }
  try {
    await api(
      `/training/datasets/${state.selectedDatasetId}/annotation-versions/${state.selectedVersionId}/annotations/${state.selectedImageId}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state.annotations),
      }
    );
    notify("annotations saved");
  } catch (e) {
    notify(e.message);
  }
}

async function fetchModelSources() {
  const preset = ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"];
  const select = document.getElementById("train-model");
  select.innerHTML = "";
  try {
    const data = await api("/models");
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
  if (!state.selectedDatasetId) return notify("select a dataset first");
  const annotation_version_id = document.getElementById("train-version").value;
  if (!annotation_version_id) return notify("select annotation version");

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
    const job = await api("/training/jobs/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.activeJobId = job.id;
    state.logOffset = 0;
    document.getElementById("training-logs").textContent = "";
    notify("training started");
  } catch (e) {
    notify(e.message);
  }
}

async function stopTraining() {
  if (!state.activeJobId) return notify("no active training job");
  try {
    await api(`/training/jobs/${state.activeJobId}/stop`, { method: "POST" });
    notify("stop requested");
  } catch (e) {
    notify(e.message);
  }
}

async function pollJobs() {
  if (state.trainingApiUnavailable) return;
  try {
    const data = await api("/training/jobs");
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
    const msg = (e && e.message) ? e.message : "";
    if (msg.includes("404")) {
      state.trainingApiUnavailable = true;
      if (state.jobPollTimer) {
        clearInterval(state.jobPollTimer);
        state.jobPollTimer = null;
      }
      const statusEl = document.getElementById("training-status");
      statusEl.textContent = "Training API unavailable (404). Restart backend to enable training features.";
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
  const data = await api(`/training/jobs/${jobId}/logs?offset=${state.logOffset}`);
  const logsEl = document.getElementById("training-logs");
  if (data.chunk) {
    logsEl.textContent += data.chunk;
    logsEl.scrollTop = logsEl.scrollHeight;
  }
  state.logOffset = data.next_offset || state.logOffset;
}
