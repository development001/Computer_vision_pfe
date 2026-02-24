document.addEventListener('DOMContentLoaded', () => {
  fetchCameras();
});

async function fetchCameras(){
  try {
    let r=await fetch('/cameras');
    let j=await r.json();
    let d=document.getElementById('cameras-list');
    d.innerHTML='';
    
    if (Object.keys(j.cameras).length === 0) {
      d.innerHTML = '<div class="empty-state">No cameras configured. Add one above.</div>';
      return;
    }

    for(const id in j.cameras){
      const cam=j.cameras[id];
      const div=document.createElement('div');
      div.className='camera-item';
      div.innerHTML=`
        <div class="camera-info">
          <span class="camera-icon">📷</span>
          <div class="camera-details">
            <span class="camera-name">${cam.name}</span>
            <span class="camera-rtsp">${cam.rtsp}</span>
          </div>
        </div>
        <div class="camera-actions">
          <button class="action-btn" onclick="startJobRedirect('${id}')">Start AI</button>
          <button class="action-btn secondary" onclick="viewRaw('${id}')">View Raw</button>
        </div>
      `;
      d.appendChild(div);
    }
  } catch (e) {
    console.error("Error fetching cameras:", e);
  }
}

async function addCamera(){
  const name=document.getElementById('cam-name').value;
  const ip=document.getElementById('cam-ip').value;
  const user=document.getElementById('cam-user').value;
  const pass=document.getElementById('cam-pass').value;
  const channel=document.getElementById('cam-channel').value;

  if(!name || !ip || !user || !pass || !channel){
    alert('Please fill in all fields');
    return;
  }

  // Generic URL construction as requested
  // rtsp://user:pass@ip:554/{channel}
  const rtsp = `rtsp://${user}:${pass}@${ip}:554/${channel}`;

  try {
    await fetch('/cameras',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,rtsp})
    });
    
    // Clear inputs
    document.getElementById('cam-name').value = '';
    document.getElementById('cam-ip').value = '';
    document.getElementById('cam-user').value = '';
    document.getElementById('cam-pass').value = '';
    document.getElementById('cam-channel').value = '';
    
    fetchCameras();
  } catch (e) {
    alert("Failed to add camera");
  }
}

function viewRaw(cam_id){
  const viewer = document.getElementById('live-view-section');
  const stream = document.getElementById('stream');
  viewer.style.display = 'block';
  stream.src = `/cameras/${cam_id}/mjpeg`;
  viewer.scrollIntoView({ behavior: 'smooth' });
}

function closeViewer() {
  const viewer = document.getElementById('live-view-section');
  const stream = document.getElementById('stream');
  stream.src = '';
  viewer.style.display = 'none';
}

function startJobRedirect(cam_id) {
  // Redirect to jobs page with pre-selected camera
  window.location.href = `/ui/jobs?camera_id=${cam_id}`;
}
