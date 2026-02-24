from flask import Flask, request, jsonify, Response, send_from_directory
from worker import TrackingWorker
from config import RTSPConfig, TrackerConfig, JobConfig
from werkzeug.utils import secure_filename
import os
import threading
import uuid
import time
import cv2
import persistence
import yaml
import json

app = Flask(__name__)

# Scan workspace root for model files by default (adjust as needed)
MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')

# Ensure models directory exists
if not os.path.exists(MODELS_DIR):
    os.makedirs(MODELS_DIR)

ALLOWED_EXTENSIONS = {'pt', 'onnx', 'engine'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def available_models():
    files = []
    try:
        for f in os.listdir(MODELS_DIR):
            if any(f.endswith('.' + ext) for ext in ALLOWED_EXTENSIONS):
                files.append(f)
    except Exception:
        pass
    return files

# In-memory stores (replace with DB later)
cameras = {}   # camera_id -> {name, rtsp}
jobs = {}      # job_id -> {camera_id, model, worker}

# Trackers directory
TRACKERS_DIR = os.path.join(os.path.dirname(__file__), 'trackers')

# Ensure trackers directory exists
if not os.path.exists(TRACKERS_DIR):
    os.makedirs(TRACKERS_DIR)

jobs_lock = threading.Lock()

# Load state from persistence
loaded_cameras, loaded_jobs_config = persistence.load_state()
cameras.update(loaded_cameras)

# Restart jobs
for jid, j_config in loaded_jobs_config.items():
    try:
        # Reconstruct configurations
        rtsp_config = RTSPConfig.from_dict(j_config)
        tracker_config = TrackerConfig.from_dict(j_config)
        
        config = JobConfig(
            camera_id=j_config['camera_id'],
            model_name=j_config['model'],
            rtsp_url=cameras[j_config['camera_id']]['rtsp'],
            conf=j_config.get('conf', 0.25),
            iou=j_config.get('iou', 0.7),
            rtsp_config=rtsp_config,
            tracker_config=tracker_config,
            line_coords=j_config.get('line_coords')
        )
        
        worker = TrackingWorker(config)
        worker.start()
        
        j_config['worker'] = worker
        jobs[jid] = j_config
        print(f"Restarted job {jid} for camera {j_config['camera_id']}")
    except Exception as e:
        print(f"Failed to restart job {jid}: {e}")

@app.route('/models', methods=['GET'])
def list_models():
    return jsonify({'models': available_models()})

@app.route('/cameras', methods=['GET'])
def list_cameras():
    return jsonify({'cameras': cameras})

@app.route('/cameras', methods=['POST'])
def add_camera():
    data = request.json or {}
    name = data.get('name') or f'cam-{len(cameras)+1}'
    rtsp = data.get('rtsp')
    if not rtsp:
        return jsonify({'error': 'rtsp field required'}), 400
    cid = str(uuid.uuid4())
    cameras[cid] = {'name': name, 'rtsp': rtsp}
    persistence.save_state(cameras, jobs, jobs_lock)
    return jsonify({'camera_id': cid}), 201

@app.route('/cameras/<camera_id>/snapshot')
def camera_snapshot(camera_id):
    cam = cameras.get(camera_id)
    if not cam:
        return jsonify({'error': 'unknown camera'}), 404
    rtsp_url = cam['rtsp']
    
    # Get RTSP configuration from request parameters
    width = request.args.get('width', type=int)
    height = request.args.get('height', type=int)
    
    rtsp_kwargs = {}
    if width: rtsp_kwargs['width'] = width
    if height: rtsp_kwargs['height'] = height
    
    # Use a temporary stream to capture a single frame
    from rtsp import RTSPVideoStream
    stream = RTSPVideoStream(rtsp_url, **rtsp_kwargs)
    stream.start()
    
    try:
        # Wait up to 5 seconds for a frame
        frame = stream.read(timeout=5.0)
            
        if frame is None:
             return jsonify({'error': 'failed to grab frame'}), 500
             
        ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
             return jsonify({'error': 'failed to encode frame'}), 500
             
        return Response(buf.tobytes(), mimetype='image/jpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        stream.stop()

@app.route('/jobs', methods=['GET'])
def list_jobs():
    with jobs_lock:
        summary = {jid: {'camera_id': j['camera_id'], 'model': j['model'], 'status': j['worker'].status} for jid, j in jobs.items()}
    return jsonify(summary)

@app.route('/jobs/start', methods=['POST'])
def start_job():
    data = request.json or {}
    camera_id = data.get('camera_id')
    model_name = data.get('model')
    
    if not camera_id or camera_id not in cameras:
        return jsonify({'error': 'unknown camera_id'}), 400
    if not model_name or model_name not in available_models():
        return jsonify({'error': 'model not available'}), 400

    try:
        rtsp_config = RTSPConfig.from_dict(data)
        tracker_config = TrackerConfig.from_dict(data)
        
        config = JobConfig(
            camera_id=camera_id,
            model_name=model_name,
            rtsp_url=cameras[camera_id]['rtsp'],
            conf=float(data.get('conf', 0.25)),
            iou=float(data.get('iou', 0.7)),
            rtsp_config=rtsp_config,
            tracker_config=tracker_config,
            line_coords=data.get('line_coords')
        )
    except Exception as e:
        return jsonify({'error': f'Invalid configuration: {str(e)}'}), 400

    jid = str(uuid.uuid4())
    worker = TrackingWorker(config)
    worker.start()
    
    with jobs_lock:
        job_data = config.to_dict()
        job_data['worker'] = worker
        jobs[jid] = job_data
        
    persistence.save_state(cameras, jobs, jobs_lock)
    response = config.to_dict()
    response['job_id'] = jid
    return jsonify(response), 201

@app.route('/jobs/stop', methods=['POST'])
def stop_job():
    data = request.json or {}
    jid = data.get('job_id')
    if not jid or jid not in jobs:
        return jsonify({'error': 'unknown job_id'}), 400
    with jobs_lock:
        worker = jobs[jid]['worker']
        worker.stop()
        del jobs[jid]
    persistence.save_state(cameras, jobs, jobs_lock)
    return jsonify({'stopped': jid})

@app.route('/jobs/<job_id>/status', methods=['GET'])
def job_status(job_id):
    j = jobs.get(job_id)
    if not j:
        return jsonify({'error': 'unknown job'}), 404
    return jsonify({'camera_id': j['camera_id'], 'model': j['model'], 'status': j['worker'].status})

@app.route('/jobs/<job_id>/mjpeg')
def mjpeg_stream(job_id):
    j = jobs.get(job_id)
    if not j:
        return 'unknown job', 404
    def generator():
        worker = j['worker']
        import time
        while worker.is_running():
            frame = getattr(worker, 'latest_jpeg', None)
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                time.sleep(0.05)
        yield b''
    return Response(generator(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/cameras/<camera_id>/mjpeg')
def camera_mjpeg(camera_id):
    cam = cameras.get(camera_id)
    if not cam:
        return 'unknown camera', 404
    rtsp_url = cam['rtsp']
    
    # We use RTSPVideoStream to handle the connection robustly
    # Note: This creates a new connection for every viewer. 
    # Ideally, you'd want a shared stream manager, but for this request we'll just use the class.
    from rtsp import RTSPVideoStream
    
    def generator():
        stream = RTSPVideoStream(rtsp_url)
        stream.start()
        try:
            while True:
                # Use a small timeout to allow checking for disconnects/interrupts
                frame = stream.read(timeout=0.5)
                if frame is None:
                    # If stream is still trying to connect, we might yield nothing or wait
                    if not stream.is_alive():
                        break
                    continue
                
                ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if not ok:
                    continue
                    
                frame_bytes = buf.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        finally:
            stream.stop()

    return Response(generator(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/models/upload', methods=['POST'])
def upload_model():
    if 'file' not in request.files:
        return jsonify({'error': 'no file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'no file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'only .pt and .onnx files allowed'}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(MODELS_DIR, filename)
    file.save(filepath)
    return jsonify({'message': 'model uploaded', 'filename': filename}), 201
 
@app.route('/models/optimize', methods=['POST'])
def optimize_model():
    data = request.json or {}
    source = data.get('source')
    target = (data.get('target') or '').lower()
    imgsz = data.get('imgsz', 640)
    opset = int(data.get('opset', 12))
    dynamic = bool(data.get('dynamic', False))
    half = bool(data.get('half', False))

    if not source:
        return jsonify({'error': 'source field required'}), 400
    if target not in ('onnx', 'tensorrt'):
        return jsonify({'error': 'target must be \"onnx\" or \"tensorrt\"'}), 400

    try:
        from services.model_optimizer import ModelOptimizer
    except Exception as e:
        return jsonify({'error': f'optimizer unavailable: {e}'}), 500
    try:
        optimizer = ModelOptimizer(MODELS_DIR)
        out_name = optimizer.optimize(source, target, imgsz=imgsz, opset=opset, dynamic=dynamic, half=half)
        return jsonify({'message': 'model optimized', 'filename': out_name, 'format': target}), 200
    except Exception as e:
        return jsonify({'error': f'optimization failed: {e}'}), 500

@app.route('/')
def index():
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    return send_from_directory(static_dir, 'index.html')

@app.route('/ui/<path:name>')
def ui_pages(name):
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    base = name[:-5] if name.endswith('.html') else name
    nested = os.path.join(base, f"{os.path.basename(base)}.html")
    nested_path = os.path.join(static_dir, nested)
    if os.path.exists(nested_path):
        subdir = os.path.join(static_dir, base)
        return send_from_directory(subdir, f"{os.path.basename(base)}.html")
    candidate = name if name.endswith('.html') else f"{name}.html"
    root_path = os.path.join(static_dir, candidate)
    if os.path.exists(root_path):
        return send_from_directory(static_dir, candidate)
    return jsonify({'error': 'page not found'}), 404

# Tracker configuration endpoints
@app.route('/trackers', methods=['GET'])
def list_trackers():
    trackers = []
    try:
        for filename in os.listdir(TRACKERS_DIR):
            if filename.endswith('.yml') or filename.endswith('.yaml'):
                filepath = os.path.join(TRACKERS_DIR, filename)
                with open(filepath, 'r') as f:
                    config = yaml.safe_load(f)
                trackers.append({
                    'name': filename.rsplit('.', 1)[0],
                    'filename': filename,
                    'config': config
                })
    except Exception as e:
        print(f"Error loading trackers: {e}")
        return jsonify({'error': 'Failed to load trackers'}), 500
    
    return jsonify(trackers)

@app.route('/trackers', methods=['POST'])
def save_tracker():
    data = request.json or {}
    name = data.get('name')
    config = data.get('config')
    
    if not name or not config:
        return jsonify({'error': 'name and config fields required'}), 400
    
    # Validate tracker type
    tracker_type = config.get('tracker_type')
    if tracker_type not in ['botsort', 'bytetrack']:
        return jsonify({'error': 'tracker_type must be botsort or bytetrack'}), 400
    
    # Sanitize filename
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_name = safe_name.replace(' ', '_')
    
    if not safe_name:
        return jsonify({'error': 'invalid tracker name'}), 400
    
    filename = f"{safe_name}.yml"
    filepath = os.path.join(TRACKERS_DIR, filename)
    
    # Check if file already exists
    if os.path.exists(filepath):
        return jsonify({'error': 'tracker with this name already exists'}), 409
    
    try:
        with open(filepath, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        return jsonify({'message': 'tracker saved', 'name': safe_name}), 201
    except Exception as e:
        print(f"Error saving tracker: {e}")
        return jsonify({'error': 'Failed to save tracker'}), 500

@app.route('/trackers/<name>', methods=['DELETE'])
def delete_tracker(name):
    # Sanitize input
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_name = safe_name.replace(' ', '_')
    
    if not safe_name:
        return jsonify({'error': 'invalid tracker name'}), 400
    
    filename = f"{safe_name}.yml"
    filepath = os.path.join(TRACKERS_DIR, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'tracker not found'}), 404
    
    try:
        os.remove(filepath)
        return jsonify({'message': 'tracker deleted', 'name': safe_name})
    except Exception as e:
        print(f"Error deleting tracker: {e}")
        return jsonify({'error': 'Failed to delete tracker'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
