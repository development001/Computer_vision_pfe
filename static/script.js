async function fetchModels(){
  let r = await fetch('/models');
  let j = await r.json();
  let s = document.getElementById('models');
  s.innerHTML='';
  j.models.forEach(m=>{
    let o=document.createElement('option');
    o.value=m; o.text=m;
    s.appendChild(o);
  });
}

async function fetchCameras(){
  let r=await fetch('/cameras');
  let j=await r.json();
  let d=document.getElementById('cameras');
  d.innerHTML='';
  for(const id in j.cameras){
    const cam=j.cameras[id];
    const div=document.createElement('div');
    div.className='camera-item';
    div.innerHTML=`
      <b>${cam.name}</b>
      <div class="small-text">${cam.rtsp}</div>
      <button onclick="startJob('${id}')">Start AI</button>
      <button onclick="viewRaw('${id}')">View Raw</button>
    `;
    d.appendChild(div);
  }
}

async function fetchJobs(){
  let r=await fetch('/jobs');
  let j=await r.json();
  let d=document.getElementById('jobs');
  d.innerHTML='';
  for(const id in j){
    const job=j[id];
    const div=document.createElement('div');
    div.className='job-item';
    div.innerHTML=`
      <b>Job:</b> ${id} 
      <span class="badge">${job.status}</span><br>
      <span class="small-text">Camera: ${job.camera_id} | Model: ${job.model}</span><br>
      <button onclick="viewAI('${id}')">View AI</button>
      <button class="danger" onclick="stopJob('${id}')">Stop</button>
    `;
    d.appendChild(div);
  }
}

async function addCamera(){
  const name=document.getElementById('cam-name').value;
  const rtsp=document.getElementById('cam-rtsp').value;
  await fetch('/cameras',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,rtsp})
  });
  fetchCameras();
}

async function startJob(camera_id){
  const model=document.getElementById('models').value;
  const imgsz=parseInt(document.getElementById('imgsz').value);
  const rtsp_width=parseInt(document.getElementById('rtsp_width').value);
  const rtsp_height=parseInt(document.getElementById('rtsp_height').value);
  const rtsp_fps=parseInt(document.getElementById('rtsp_fps').value);
  const rtsp_reconnect_delay=parseFloat(document.getElementById('rtsp_reconnect_delay').value);
  const rtsp_buffer_size=parseInt(document.getElementById('rtsp_buffer_size').value);
  const rtsp_read_timeout=parseFloat(document.getElementById('rtsp_read_timeout').value);
  const rtsp_cv2_backend=document.getElementById('rtsp_cv2_backend').value;

  await fetch('/jobs/start',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      camera_id,model,imgsz,
      rtsp_width,rtsp_height,rtsp_fps,
      rtsp_reconnect_delay,rtsp_buffer_size,
      rtsp_read_timeout,rtsp_cv2_backend
    })
  });
  fetchJobs();
}

async function stopJob(job_id){
  await fetch('/jobs/stop',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({job_id})
  });
  document.getElementById('stream').src='';
  fetchJobs();
}

function viewAI(job_id){
  document.getElementById('stream').src=`/jobs/${job_id}/mjpeg`;
}

function viewRaw(cam_id){
  document.getElementById('stream').src=`/cameras/${cam_id}/mjpeg`;
}

async function uploadModel(){
  const file=document.getElementById('model-file').files[0];
  if(!file){ alert('Select a file first'); return;}
  const formData=new FormData();
  formData.append('file',file);
  const status=document.getElementById('upload-status');
  status.innerHTML='Uploading...';
  const r=await fetch('/models/upload',{method:'POST',body:formData});
  const j=await r.json();
  if(r.ok){
    status.innerHTML='✓ Uploaded: '+j.filename;
    fetchModels();
  }else{
    status.innerHTML='✗ Error: '+j.error;
  }
}

fetchModels();
fetchCameras();
fetchJobs();
setInterval(fetchJobs,3000);
