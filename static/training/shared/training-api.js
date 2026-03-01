(function () {
  const STORAGE_KEY = "training.selectedDatasetId";

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
    const data = await api("/training/datasets");
    return data.datasets || [];
  }

  function getStoredDatasetId() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  }

  function setStoredDatasetId(datasetId) {
    try {
      if (datasetId) {
        localStorage.setItem(STORAGE_KEY, datasetId);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Ignore localStorage failures.
    }
  }

  function resolveDatasetId(datasets, preferredId) {
    if (!datasets.length) return null;
    if (preferredId && datasets.some((d) => d.id === preferredId)) return preferredId;
    return datasets[0].id;
  }

  function populateDatasetSelect(selectEl, datasets, selectedId, emptyLabel = "No datasets") {
    selectEl.innerHTML = "";
    if (!datasets.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = emptyLabel;
      selectEl.appendChild(opt);
      return;
    }

    datasets.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = d.name;
      selectEl.appendChild(opt);
    });

    if (selectedId) {
      selectEl.value = selectedId;
    }
  }

  function datasetLabel(dataset) {
    return `${dataset.image_count} images, ${dataset.class_count} classes, ${dataset.annotation_version_count} versions`;
  }

  window.TrainingShared = {
    notify,
    api,
    fetchDatasets,
    getStoredDatasetId,
    setStoredDatasetId,
    resolveDatasetId,
    populateDatasetSelect,
    datasetLabel,
  };
})();
