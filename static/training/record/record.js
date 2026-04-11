const api = window.TrainingApi || {};

let recordingState = {};
let activeCameraId = null;

document.addEventListener('DOMContentLoaded', () => {
  initializeControls();
  loadCameras();
  loadRecordingSettings();
  updateRecordingStatus();
  setInterval(updateRecordingStatus, 2000);
});

function initializeControls() {
  const resolutionMode = document.getElementById('resolution-mode');
  const customResolution = document.querySelector('.custom-resolution');
  const widthInput = document.getElementById('custom-width');
  const heightInput = document.getElementById('custom-height');

  if (resolutionMode) {
    resolutionMode.addEventListener('change', () => {
      const isCustom = resolutionMode.value === 'custom';
      customResolution.style.display = isCustom ? 'grid' : 'none';
      widthInput.disabled = !isCustom;
      heightInput.disabled = !isCustom;
      if (!isCustom) {
        widthInput.value = '';
        heightInput.value = '';
      }
    });
  }

  document.getElementById('start-recording-btn').addEventListener('click', startRecording);
  document.getElementById('stop-recording-btn').addEventListener('click', stopRecording);
  document.getElementById('close-preview-btn').addEventListener('click', closePreview);

  const prefixInput = document.getElementById('record-prefix');
  if (prefixInput) {
    prefixInput.addEventListener('blur', saveRecordingSettings);
  }
}

async function loadCameras() {
  try {
    const response = await fetch('/training/record/cameras');
    const data = await response.json();
    const cameraSelect = document.getElementById('camera-select');
    
    cameraSelect.innerHTML = '<option value="">-- Choose a camera --</option>';
    
    if (data.cameras && Object.keys(data.cameras).length > 0) {
      for (const [id, cam] of Object.entries(data.cameras)) {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = cam.name;
        cameraSelect.appendChild(option);
      }
    } else {
      const option = document.createElement('option');
      option.disabled = true;
      option.textContent = 'No cameras available';
      cameraSelect.appendChild(option);
    }
  } catch (error) {
    console.error('Failed to load cameras:', error);
    setStatus('Failed to load cameras', true);
  }
}

function getRecordingPayload() {
  const prefix = (document.getElementById('record-prefix').value || '').trim();
  const resolutionMode = document.getElementById('resolution-mode').value;
  const width = resolutionMode === 'custom' ? document.getElementById('custom-width').value : null;
  const height = resolutionMode === 'custom' ? document.getElementById('custom-height').value : null;

  let validWidth = null;
  let validHeight = null;

  if (width || height) {
    try {
      validWidth = parseInt(width, 10);
      validHeight = parseInt(height, 10);
      if (!Number.isInteger(validWidth) || validWidth <= 0 || !Number.isInteger(validHeight) || validHeight <= 0) {
        throw new Error('Width and height must be positive integers');
      }
    } catch (e) {
      alert('For custom resolution, enter valid width and height values.');
      return null;
    }
  }

  return {
    filename_prefix: prefix || null,
    width: validWidth,
    height: validHeight
  };
}

async function startRecording() {
  const cameraId = document.getElementById('camera-select').value;
  
  if (!cameraId) {
    alert('Please select a camera');
    return;
  }

  const payload = getRecordingPayload();
  if (!payload) return;

  activeCameraId = cameraId;
  setStatus('Starting recording...');

  try {
    const response = await fetch(`/training/record/${cameraId}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to start recording');
    }

    saveRecordingSettings();
    setStatus(`Recording started for ${data.camera_id}`);
    updateButtonState();
    updateRecordingStatus();
  } catch (error) {
    setStatus(error.message, true);
    activeCameraId = null;
  }
}

async function stopRecording() {
  if (!activeCameraId) return;

  setStatus('Stopping recording...');

  try {
    const response = await fetch(`/training/record/${activeCameraId}/stop`, {
      method: 'POST'
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to stop recording');
    }

    const status = data.status || {};
    const message = status.output_path 
      ? `Recording stopped. Saved to: ${status.output_path}`
      : 'Recording stopped.';
    setStatus(message);
    
    activeCameraId = null;
    updateButtonState();
    updateRecordingStatus();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function updateRecordingStatus() {
  try {
    const response = await fetch('/training/record/status');
    const data = await response.json();

    recordingState = data.recordings || {};
    renderRecordings(recordingState);
    updateButtonState();
  } catch (error) {
    console.error('Failed to update recording status:', error);
  }
}

function renderRecordings(recordings) {
  const list = document.getElementById('recordings-list');
  
  if (!recordings || Object.keys(recordings).length === 0) {
    list.innerHTML = '<div class="empty-state">No active recordings.</div>';
    return;
  }

  list.innerHTML = '';
  
  for (const [camId, status] of Object.entries(recordings)) {
    if (!status.recording) continue;

    const item = document.createElement('div');
    item.className = 'recording-item';
    item.innerHTML = `
      <div class="recording-info">
        <div class="recording-camera">${status.camera_id}</div>
        <div class="recording-details">
          <span class="detail-label">Frames:</span> <span>${status.frame_count}</span>
          <span class="detail-label">FPS:</span> <span>${(status.fps || 0).toFixed(1)}</span>
          ${status.output_path ? `<span class="detail-label">File:</span> <span class="file-path">${status.output_path}</span>` : ''}
        </div>
      </div>
      <button class="action-btn view-btn" onclick="viewPreview('${camId}')">View</button>
    `;
    list.appendChild(item);
  }
}

function viewPreview(cameraId) {
  const previewSection = document.getElementById('preview-section');
  const previewImg = document.getElementById('preview-img');
  previewImg.src = `/cameras/${cameraId}/mjpeg`;
  previewSection.style.display = 'block';
  previewSection.scrollIntoView({ behavior: 'smooth' });
}

function closePreview() {
  const previewSection = document.getElementById('preview-section');
  const previewImg = document.getElementById('preview-img');
  previewImg.src = '';
  previewSection.style.display = 'none';
}

function updateButtonState() {
  const hasActiveRecording = Object.values(recordingState).some(r => r.recording);
  const startBtn = document.getElementById('start-recording-btn');
  const stopBtn = document.getElementById('stop-recording-btn');

  startBtn.style.display = hasActiveRecording ? 'none' : 'block';
  stopBtn.style.display = hasActiveRecording ? 'block' : 'none';
}

function setStatus(message, isError = false) {
  const statusEl = document.getElementById('record-status');
  statusEl.textContent = message;
  statusEl.className = isError ? 'status-message error' : 'status-message';
}

function saveRecordingSettings() {
  try {
    const settings = {
      filename_prefix: (document.getElementById('record-prefix').value || '').trim()
    };
    localStorage.setItem('training_record_settings_v1', JSON.stringify(settings));
  } catch (_) {
    // Ignore localStorage errors
  }
}

function loadRecordingSettings() {
  try {
    const raw = localStorage.getItem('training_record_settings_v1');
    if (!raw) return;
    const data = JSON.parse(raw);
    if (typeof data.filename_prefix === 'string') {
      document.getElementById('record-prefix').value = data.filename_prefix;
    }
  } catch (_) {
    // Ignore broken local storage values
  }
}
