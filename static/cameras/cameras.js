let recordingStatuses = {};

document.addEventListener('DOMContentLoaded', () => {
  initRawResolutionControls();
  initRecordingControls();
  setRecordStatus('Ready to record. Videos are stored in server default folder: server/data/recordings');
  fetchCameras();
  setInterval(fetchCameras, 4000);
});

function initRawResolutionControls() {
  const mode = document.getElementById('raw-resolution-mode');
  const width = document.getElementById('raw-width');
  const height = document.getElementById('raw-height');
  if (!mode || !width || !height) return;

  mode.addEventListener('change', () => {
    const isCustom = mode.value === 'custom';
    width.disabled = !isCustom;
    height.disabled = !isCustom;
    if (!isCustom) {
      width.value = '';
      height.value = '';
    }
  });
}

function initRecordingControls() {
  ['record-filename-prefix'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', persistRecordingSettings);
      el.addEventListener('blur', persistRecordingSettings);
    }
  });

  loadRecordingSettings();
}

async function fetchCameras() {
  try {
    const [camRes, recRes] = await Promise.all([
      fetch('/cameras'),
      fetch('/cameras/recordings/status')
    ]);

    const camData = await camRes.json();
    const recData = await recRes.json().catch(() => ({ recordings: {} }));
    recordingStatuses = recData.recordings || {};

    const listEl = document.getElementById('cameras-list');
    listEl.innerHTML = '';

    if (!camData.cameras || Object.keys(camData.cameras).length === 0) {
      listEl.innerHTML = '<div class="empty-state">No cameras configured. Add one above.</div>';
      return;
    }

    const activeRecordings = Object.values(recordingStatuses).filter((r) => r.recording).length;
    if (activeRecordings > 0) {
      const firstWithPath = Object.values(recordingStatuses).find((r) => r.recording && r.output_path);
      if (firstWithPath && firstWithPath.output_path) {
        setRecordStatus(`${activeRecordings} recording(s) active. Saving to: ${firstWithPath.output_path}`);
      } else {
        setRecordStatus(`${activeRecordings} recording(s) active. Files are saved in server/data/recordings`);
      }
    }

    for (const id in camData.cameras) {
      const cam = camData.cameras[id];
      const recState = recordingStatuses[id] || {};
      const isRecording = !!recState.recording;

      const item = document.createElement('div');
      item.className = 'camera-item';
      item.innerHTML = `
        <div class="camera-info">
          <span class="camera-icon">CA</span>
          <div class="camera-details">
            <span class="camera-name">${cam.name} ${isRecording ? '<span class="recording-badge">REC</span>' : ''}</span>
            <span class="camera-rtsp">${cam.rtsp}</span>
          </div>
        </div>
        <div class="camera-actions">
          <button class="action-btn" onclick="startJobRedirect('${id}')">Start AI</button>
          <button class="action-btn secondary" onclick="viewRaw('${id}')">View Raw</button>
          <button class="action-btn ${isRecording ? 'recording' : 'record'}" onclick="toggleRecording('${id}')">${isRecording ? 'Stop Rec' : 'Record'}</button>
        </div>
      `;
      listEl.appendChild(item);
    }
  } catch (e) {
    console.error('Error fetching cameras:', e);
  }
}

async function addCamera() {
  const name = document.getElementById('cam-name').value;
  const ip = document.getElementById('cam-ip').value;
  const user = document.getElementById('cam-user').value;
  const pass = document.getElementById('cam-pass').value;
  const channel = document.getElementById('cam-channel').value;

  if (!name || !ip || !user || !pass || !channel) {
    alert('Please fill in all fields');
    return;
  }

  const rtsp = `rtsp://${user}:${pass}@${ip}:554/${channel}`;

  try {
    await fetch('/cameras', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, rtsp })
    });

    document.getElementById('cam-name').value = '';
    document.getElementById('cam-ip').value = '';
    document.getElementById('cam-user').value = '';
    document.getElementById('cam-pass').value = '';
    document.getElementById('cam-channel').value = '';

    fetchCameras();
  } catch (e) {
    alert('Failed to add camera');
  }
}

function getRawStreamParams() {
  const mode = document.getElementById('raw-resolution-mode');
  const widthInput = document.getElementById('raw-width');
  const heightInput = document.getElementById('raw-height');

  if (!mode || !widthInput || !heightInput) return '';
  if (mode.value !== 'custom') return '';

  const width = parseInt(widthInput.value, 10);
  const height = parseInt(heightInput.value, 10);

  if (!Number.isInteger(width) || width <= 0 || !Number.isInteger(height) || height <= 0) {
    alert('For custom raw stream resolution, enter valid width and height values.');
    return null;
  }

  return `?width=${width}&height=${height}`;
}

function viewRaw(cam_id) {
  const query = getRawStreamParams();
  if (query === null) return;

  const viewer = document.getElementById('live-view-section');
  const stream = document.getElementById('stream');
  viewer.style.display = 'block';
  stream.src = `/cameras/${cam_id}/mjpeg${query || ''}`;
  viewer.scrollIntoView({ behavior: 'smooth' });
}

function getRecordingPayload() {
  const filenamePrefix = (document.getElementById('record-filename-prefix')?.value || '').trim();

  const mode = document.getElementById('raw-resolution-mode');
  const widthInput = document.getElementById('raw-width');
  const heightInput = document.getElementById('raw-height');
  let width = null;
  let height = null;

  if (mode && mode.value === 'custom') {
    width = parseInt(widthInput.value, 10);
    height = parseInt(heightInput.value, 10);
    if (!Number.isInteger(width) || width <= 0 || !Number.isInteger(height) || height <= 0) {
      alert('For custom recording resolution, enter valid width and height values.');
      return null;
    }
  }

  return {
    filename_prefix: filenamePrefix || null,
    width,
    height
  };
}

async function toggleRecording(cam_id) {
  const recState = recordingStatuses[cam_id] || {};
  const isRecording = !!recState.recording;

  try {
    if (isRecording) {
      setRecordStatus('Stopping recording...');
      const res = await fetch(`/cameras/${cam_id}/recording/stop`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || 'failed to stop recording');

      const status = data.status || {};
      const out = status.output_path ? ` Saved: ${status.output_path}` : '';
      setRecordStatus(`Recording stopped.${out}`);
    } else {
      const payload = getRecordingPayload();
      if (!payload) return;
      persistRecordingSettings();

      setRecordStatus('Starting recording...');
      const res = await fetch(`/cameras/${cam_id}/recording/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || 'failed to start recording');

      setRecordStatus(`Recording started. Video will be saved in: ${data.output_dir}`);
    }

    fetchCameras();
  } catch (e) {
    setRecordStatus(e.message || 'recording action failed', true);
  }
}

function closeViewer() {
  const viewer = document.getElementById('live-view-section');
  const stream = document.getElementById('stream');
  stream.src = '';
  viewer.style.display = 'none';
}

function startJobRedirect(cam_id) {
  window.location.href = `/ui/jobs?camera_id=${cam_id}`;
}

function setRecordStatus(message, isError = false) {
  const el = document.getElementById('record-status');
  if (!el) return;
  el.textContent = message;
  el.classList.toggle('error', !!isError);
}

function persistRecordingSettings() {
  const payload = {
    filename_prefix: (document.getElementById('record-filename-prefix')?.value || '').trim()
  };
  try {
    localStorage.setItem('camera_record_settings_v1', JSON.stringify(payload));
  } catch (_) {
    // Ignore localStorage errors.
  }
}

function loadRecordingSettings() {
  try {
    const raw = localStorage.getItem('camera_record_settings_v1');
    if (!raw) return;
    const data = JSON.parse(raw);
    if (typeof data.filename_prefix === 'string') {
      document.getElementById('record-filename-prefix').value = data.filename_prefix;
    }
  } catch (_) {
    // Ignore broken local storage values.
  }
}
