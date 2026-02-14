from flask import Flask, request, jsonify, Response, send_from_directory
from worker import TrackingWorker
from werkzeug.utils import secure_filename
import os
import threading
import uuid
import time
import cv2

app = Flask(__name__)

# Scan workspace root for model files by default (adjust as needed)
MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')

# Ensure models directory exists
if not os.path.exists(MODELS_DIR):
    os.makedirs(MODELS_DIR)

ALLOWED_EXTENSIONS = {'pt', 'onnx'}

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

jobs_lock = threading.Lock()

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
    return jsonify({'camera_id': cid}), 201

@app.route('/jobs', methods=['GET'])
def list_jobs():
    with jobs_lock:
        summary = {jid: {'camera_id': j['camera_id'], 'model': j['model'], 'imgsz': j.get('imgsz', 640), 'status': j['worker'].status} for jid, j in jobs.items()}
    return jsonify(summary)

@app.route('/jobs/start', methods=['POST'])
def start_job():
    data = request.json or {}
    camera_id = data.get('camera_id')
    model_name = data.get('model')
    # optional imgsz/resize (int, e.g. 640, 480, 320)
    try:
        imgsz = int(data.get('imgsz', 640))
    except Exception:
        return jsonify({'error': 'invalid imgsz value'}), 400

    # RTSP configuration parameters with defaults
    rtsp_width = int(data.get('rtsp_width', 640))
    rtsp_height = int(data.get('rtsp_height', 640))
    rtsp_fps = int(data.get('rtsp_fps', 15))
    rtsp_reconnect_delay = float(data.get('rtsp_reconnect_delay', 3.0))
    rtsp_buffer_size = int(data.get('rtsp_buffer_size', 1))
    rtsp_read_timeout = float(data.get('rtsp_read_timeout', 5.0))
    rtsp_cv2_backend = data.get('rtsp_cv2_backend')

    if camera_id not in cameras:
        return jsonify({'error': 'unknown camera_id'}), 400
    if model_name not in available_models():
        return jsonify({'error': 'model not available'}), 400

    jid = str(uuid.uuid4())
    worker = TrackingWorker(
        cameras[camera_id]['rtsp'], 
        model_name, 
        imgsz=imgsz,
        rtsp_width=rtsp_width,
        rtsp_height=rtsp_height,
        rtsp_fps=rtsp_fps,
        rtsp_reconnect_delay=rtsp_reconnect_delay,
        rtsp_buffer_size=rtsp_buffer_size,
        rtsp_read_timeout=rtsp_read_timeout,
        rtsp_cv2_backend=rtsp_cv2_backend
    )
    worker.start()
    with jobs_lock:
        jobs[jid] = {
            'camera_id': camera_id, 
            'model': model_name, 
            'imgsz': imgsz,
            'rtsp_width': rtsp_width,
            'rtsp_height': rtsp_height,
            'rtsp_fps': rtsp_fps,
            'rtsp_reconnect_delay': rtsp_reconnect_delay,
            'rtsp_buffer_size': rtsp_buffer_size,
            'rtsp_read_timeout': rtsp_read_timeout,
            'rtsp_cv2_backend': rtsp_cv2_backend,
            'worker': worker
        }
    return jsonify({
        'job_id': jid, 
        'imgsz': imgsz,
        'rtsp_width': rtsp_width,
        'rtsp_height': rtsp_height,
        'rtsp_fps': rtsp_fps,
        'rtsp_reconnect_delay': rtsp_reconnect_delay,
        'rtsp_buffer_size': rtsp_buffer_size,
        'rtsp_read_timeout': rtsp_read_timeout,
        'rtsp_cv2_backend': rtsp_cv2_backend
    }), 201

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
    rtsp = cam['rtsp']
    def generator():
        cap = cv2.VideoCapture(rtsp)
        if not cap.isOpened():
            yield b''
            return
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue
                ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if not ok:
                    continue
                frame_bytes = buf.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        finally:
            cap.release()
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

@app.route('/')
def index():
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    return send_from_directory(static_dir, 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
