document.addEventListener('DOMContentLoaded', () => {
  fetchModels();

  const fileInput = document.getElementById('model-file');
  const fileName = document.getElementById('file-name');

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      fileName.textContent = fileInput.files[0].name;
    } else {
      fileName.textContent = '';
    }
  });
});

async function fetchModels(){
  try {
    let r = await fetch('/models');
    let j = await r.json();
    let s = document.getElementById('models-list');
    s.innerHTML='';
    if (j.models.length === 0) {
      s.innerHTML = '<li class="empty-state">No models found. Upload one to get started.</li>';
      return;
    }
    j.models.forEach(m=>{
      let li = document.createElement('li');
      li.className = 'model-item';
      li.innerHTML = `
        <span class="model-icon">🧠</span>
        <span class="model-name">${m}</span>
        <span class="model-tag">YOLO</span>
      `;
      s.appendChild(li);
    });
  } catch (e) {
    console.error("Error fetching models:", e);
  }
}

async function uploadModel(){
  const file = document.getElementById('model-file').files[0];
  if(!file){ alert('Select a file first'); return;}
  
  const formData = new FormData();
  formData.append('file', file);
  
  const status = document.getElementById('upload-status');
  status.innerHTML = '<span class="loading">Uploading...</span>';
  status.className = 'status-text loading';
  
  try {
    const r = await fetch('/models/upload', {method:'POST', body:formData});
    const j = await r.json();
    
    if(r.ok){
      status.innerHTML = '✓ Uploaded: ' + j.filename;
      status.className = 'status-text success';
      document.getElementById('file-name').textContent = '';
      document.getElementById('model-file').value = ''; // Reset input
      fetchModels();
    }else{
      status.innerHTML = '✗ Error: ' + j.error;
      status.className = 'status-text error';
    }
  } catch (e) {
    status.innerHTML = '✗ Network Error';
    status.className = 'status-text error';
  }
}
