const state = {
  datasets: [],
  selectedDatasetId: null,
  classes: [],
};

const t = window.TrainingShared;

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  initialize();
});

function bindEvents() {
  document.getElementById("dataset-select").addEventListener("change", onDatasetChange);
  document.getElementById("add-class-btn").addEventListener("click", addClass);
}

async function initialize() {
  try {
    state.datasets = await t.fetchDatasets();
    state.selectedDatasetId = t.resolveDatasetId(state.datasets, t.getStoredDatasetId());
    t.setStoredDatasetId(state.selectedDatasetId);
    renderDatasetSelect();
    await fetchClasses();
  } catch (e) {
    t.notify(e.message);
  }
}

function renderDatasetSelect() {
  const select = document.getElementById("dataset-select");
  t.populateDatasetSelect(select, state.datasets, state.selectedDatasetId, "No datasets available");

  const info = document.getElementById("dataset-selected-info");
  if (!state.selectedDatasetId) {
    info.textContent = "Create a dataset in Upload Data page first.";
    return;
  }

  const ds = state.datasets.find((d) => d.id === state.selectedDatasetId);
  info.textContent = ds ? `${ds.name} - ${ds.description || "No description"}` : "";
}

async function onDatasetChange() {
  state.selectedDatasetId = document.getElementById("dataset-select").value || null;
  t.setStoredDatasetId(state.selectedDatasetId);
  renderDatasetSelect();
  await fetchClasses();
}

async function fetchClasses() {
  if (!state.selectedDatasetId) {
    state.classes = [];
    renderClasses();
    return;
  }

  try {
    const data = await t.api(`/training/datasets/${state.selectedDatasetId}/classes`);
    state.classes = data.classes || [];
    renderClasses();
  } catch (e) {
    t.notify(e.message);
  }
}

function renderClasses() {
  const list = document.getElementById("classes-list");
  list.innerHTML = "";
  state.classes.forEach((c) => {
    const row = document.createElement("div");
    row.className = "list-item";
    row.innerHTML = `
      <div><span class="dot" style="background:${c.color};"></span>${c.id}: ${c.name}</div>
      <div class="item-actions">
        <button class="btn btn-secondary">Edit</button>
        <button class="btn btn-secondary">Delete</button>
      </div>
    `;
    const [editBtn, deleteBtn] = row.querySelectorAll("button");
    editBtn.onclick = () => editClass(c);
    deleteBtn.onclick = () => removeClass(c.id);
    list.appendChild(row);
  });
}

async function addClass() {
  if (!state.selectedDatasetId) return t.notify("select a dataset first");
  const name = document.getElementById("class-name").value.trim();
  const color = document.getElementById("class-color").value;
  if (!name) return t.notify("class name is required");

  try {
    await t.api(`/training/datasets/${state.selectedDatasetId}/classes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, color }),
    });
    document.getElementById("class-name").value = "";
    await fetchClasses();
  } catch (e) {
    t.notify(e.message);
  }
}

async function editClass(cls) {
  const name = prompt("New class name:", cls.name);
  if (name === null) return;
  const color = prompt("New color (hex):", cls.color);
  if (color === null) return;

  try {
    await t.api(`/training/datasets/${state.selectedDatasetId}/classes/${cls.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, color }),
    });
    await fetchClasses();
  } catch (e) {
    t.notify(e.message);
  }
}

async function removeClass(classId) {
  if (!confirm("Delete this class? This is blocked if used in annotations.")) return;
  try {
    await t.api(`/training/datasets/${state.selectedDatasetId}/classes/${classId}`, { method: "DELETE" });
    await fetchClasses();
  } catch (e) {
    t.notify(e.message);
  }
}
