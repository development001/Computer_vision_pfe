const state = {
  datasets: [],
  selectedDatasetId: null,
  images: [],
};

const t = window.TrainingShared;

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  initialize();
});

function bindEvents() {
  document.getElementById("create-dataset-btn").addEventListener("click", createDataset);
  document.getElementById("upload-images-btn").addEventListener("click", uploadImages);
}

async function initialize() {
  try {
    state.datasets = await t.fetchDatasets();
    state.selectedDatasetId = t.resolveDatasetId(state.datasets, t.getStoredDatasetId());
    t.setStoredDatasetId(state.selectedDatasetId);
    renderDatasets();
    await fetchImages();
  } catch (e) {
    t.notify(e.message);
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
        <small>${t.datasetLabel(d)}</small>
      </div>
      <div class="item-actions">
        <button class="btn btn-secondary">Open</button>
        <button class="btn btn-secondary">Delete</button>
      </div>
    `;
    const [openBtn, deleteBtn] = row.querySelectorAll("button");
    openBtn.onclick = async () => {
      state.selectedDatasetId = d.id;
      t.setStoredDatasetId(state.selectedDatasetId);
      renderDatasets();
      await fetchImages();
    };
    deleteBtn.onclick = () => deleteDataset(d.id);
    el.appendChild(row);
  });
}

async function createDataset() {
  const name = document.getElementById("dataset-name").value.trim();
  const description = document.getElementById("dataset-description").value.trim();
  if (!name) return t.notify("dataset name is required");

  try {
    const d = await t.api("/training/datasets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    document.getElementById("dataset-name").value = "";
    document.getElementById("dataset-description").value = "";
    state.datasets = await t.fetchDatasets();
    state.selectedDatasetId = d.id;
    t.setStoredDatasetId(state.selectedDatasetId);
    renderDatasets();
    await fetchImages();
  } catch (e) {
    t.notify(e.message);
  }
}

async function deleteDataset(datasetId) {
  if (!confirm("Delete this dataset and all related files?")) return;
  try {
    await t.api(`/training/datasets/${datasetId}`, { method: "DELETE" });
    state.datasets = await t.fetchDatasets();
    state.selectedDatasetId = t.resolveDatasetId(state.datasets, state.selectedDatasetId === datasetId ? null : state.selectedDatasetId);
    t.setStoredDatasetId(state.selectedDatasetId);
    renderDatasets();
    await fetchImages();
  } catch (e) {
    t.notify(e.message);
  }
}

async function fetchImages() {
  const info = document.getElementById("dataset-selected-info");
  const list = document.getElementById("images-list");
  list.innerHTML = "";

  if (!state.selectedDatasetId) {
    info.textContent = "Select a dataset to manage images.";
    state.images = [];
    return;
  }

  const ds = state.datasets.find((d) => d.id === state.selectedDatasetId);
  info.textContent = `${ds ? ds.name : "Dataset"} - upload and delete images here.`;

  try {
    const data = await t.api(`/training/datasets/${state.selectedDatasetId}/images`);
    state.images = data.images || [];
    renderImages();
  } catch (e) {
    t.notify(e.message);
  }
}

function renderImages() {
  const list = document.getElementById("images-list");
  list.innerHTML = "";
  state.images.forEach((img) => {
    const row = document.createElement("div");
    row.className = "list-item image-item";
    row.innerHTML = `
      <img class="image-thumb" src="${img.url}" alt="${img.original_name}" loading="lazy" />
      <div class="image-meta">
        <span class="image-name">${img.original_name}</span>
      </div>
      <div class="item-actions">
        <button class="btn btn-secondary">Delete</button>
      </div>
    `;
    row.querySelector("button").onclick = () => deleteImage(img.id);
    list.appendChild(row);
  });
}

async function uploadImages() {
  if (!state.selectedDatasetId) return t.notify("select a dataset first");
  const input = document.getElementById("image-upload");
  if (!input.files || input.files.length === 0) return t.notify("select images first");
  const form = new FormData();
  for (const f of input.files) form.append("files", f);

  try {
    await t.api(`/training/datasets/${state.selectedDatasetId}/images`, { method: "POST", body: form });
    input.value = "";
    state.datasets = await t.fetchDatasets();
    renderDatasets();
    await fetchImages();
  } catch (e) {
    t.notify(e.message);
  }
}

async function deleteImage(imageId) {
  if (!confirm("Delete this image and all its labels?")) return;
  try {
    await t.api(`/training/datasets/${state.selectedDatasetId}/images/${imageId}`, { method: "DELETE" });
    state.datasets = await t.fetchDatasets();
    renderDatasets();
    await fetchImages();
  } catch (e) {
    t.notify(e.message);
  }
}
