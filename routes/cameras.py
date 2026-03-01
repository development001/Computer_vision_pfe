from flask import Blueprint, jsonify, request, Response
import uuid
import cv2
import os
import threading
from datetime import datetime
import persistence

DEFAULT_RECORDINGS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'recordings')
)


class RawVideoRecorder(threading.Thread):
    def __init__(self, camera_id, rtsp_url, output_dir, filename_prefix='recording', width=None, height=None):
        super().__init__(daemon=True)
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.output_dir = os.path.abspath(output_dir)
        self.filename_prefix = (filename_prefix or 'recording').strip()
        self.fps = None
        self.width = int(width) if width else None
        self.height = int(height) if height else None

        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.output_path = None
        self.frame_count = 0
        self.last_error = None
        self.started_at = datetime.utcnow().isoformat()

    def stop(self):
        self._stop_event.set()

    def status(self):
        with self._lock:
            return {
                'camera_id': self.camera_id,
                'recording': self.is_alive(),
                'output_path': self.output_path,
                'frame_count': self.frame_count,
                'fps': self.fps,
                'width': self.width,
                'height': self.height,
                'started_at': self.started_at,
                'error': self.last_error,
            }

    def _create_writer(self, frame_w, frame_h, fps):
        os.makedirs(self.output_dir, exist_ok=True)
        safe_prefix = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in self.filename_prefix)
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        base_name = f"{safe_prefix}_{ts}"

        mp4_path = os.path.join(self.output_dir, f"{base_name}.mp4")
        mp4_writer = cv2.VideoWriter(
            mp4_path,
            cv2.VideoWriter_fourcc(*'mp4v'),
            float(fps),
            (frame_w, frame_h)
        )
        if mp4_writer.isOpened():
            return mp4_writer, mp4_path
        mp4_writer.release()

        avi_path = os.path.join(self.output_dir, f"{base_name}.avi")
        avi_writer = cv2.VideoWriter(
            avi_path,
            cv2.VideoWriter_fourcc(*'XVID'),
            float(fps),
            (frame_w, frame_h)
        )
        if avi_writer.isOpened():
            return avi_writer, avi_path
        avi_writer.release()

        return None, None

    def run(self):
        writer = None
        cap = None
        try:
            cap = cv2.VideoCapture(self.rtsp_url)
            if not cap.isOpened():
                with self._lock:
                    self.last_error = 'failed to open camera stream'
                return

            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                if self.width and self.height and (frame.shape[1] != self.width or frame.shape[0] != self.height):
                    frame = cv2.resize(frame, (self.width, self.height))

                if writer is None:
                    frame_h, frame_w = frame.shape[:2]
                    source_fps = cap.get(cv2.CAP_PROP_FPS)
                    source_fps = float(source_fps) if source_fps and source_fps > 1 else 0.0
                    writer_fps = min(source_fps, 60.0) if source_fps > 0 else 30.0
                    self.fps = writer_fps

                    writer, path = self._create_writer(frame_w, frame_h, writer_fps)
                    if writer is None:
                        with self._lock:
                            self.last_error = 'failed to initialize video writer'
                        break
                    with self._lock:
                        self.output_path = path

                writer.write(frame)
                with self._lock:
                    self.frame_count += 1
        except Exception as e:
            with self._lock:
                self.last_error = str(e)
        finally:
            try:
                if writer is not None:
                    writer.release()
            except Exception:
                pass
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                pass


def create_cameras_blueprint(cameras, jobs, jobs_lock):
    bp = Blueprint('cameras', __name__, url_prefix='/cameras')
    recordings = {}
    recordings_lock = threading.Lock()

    @bp.route('', methods=['GET'])
    def list_cameras():
        return jsonify({'cameras': cameras})

    @bp.route('', methods=['POST'])
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

    @bp.route('/<camera_id>/snapshot', methods=['GET'])
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

    @bp.route('/<camera_id>/mjpeg', methods=['GET'])
    def camera_mjpeg(camera_id):
        cam = cameras.get(camera_id)
        if not cam:
            return 'unknown camera', 404
        rtsp_url = cam['rtsp']

        width = request.args.get('width', type=int)
        height = request.args.get('height', type=int)
        if (width and not height) or (height and not width):
            return jsonify({'error': 'width and height must be provided together'}), 400
        rtsp_kwargs = {}
        if width and height:
            rtsp_kwargs['width'] = width
            rtsp_kwargs['height'] = height
        
        from rtsp import RTSPVideoStream
        
        def generator():
            stream = RTSPVideoStream(rtsp_url, **rtsp_kwargs)
            stream.start()
            try:
                while True:
                    frame = stream.read(timeout=0.5)
                    if frame is None:
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

    @bp.route('/recordings/status', methods=['GET'])
    def recordings_status():
        statuses = {}
        stale_ids = []
        with recordings_lock:
            for cam_id, recorder in recordings.items():
                statuses[cam_id] = recorder.status()
                if not recorder.is_alive():
                    stale_ids.append(cam_id)
            for cam_id in stale_ids:
                recordings.pop(cam_id, None)
        return jsonify({'recordings': statuses, 'default_output_dir': DEFAULT_RECORDINGS_DIR})

    @bp.route('/<camera_id>/recording/start', methods=['POST'])
    def start_recording(camera_id):
        cam = cameras.get(camera_id)
        if not cam:
            return jsonify({'error': 'unknown camera'}), 404

        data = request.json or {}
        output_dir = os.path.abspath(DEFAULT_RECORDINGS_DIR)
        filename_prefix = (data.get('filename_prefix') or cam.get('name') or 'recording').strip()

        width_raw = data.get('width')
        height_raw = data.get('height')
        try:
            width = int(width_raw) if width_raw not in (None, '') else None
            height = int(height_raw) if height_raw not in (None, '') else None
        except Exception:
            return jsonify({'error': 'width and height must be integers'}), 400
        if (width is None) != (height is None):
            return jsonify({'error': 'width and height must be provided together'}), 400
        if width is not None and (width <= 0 or height <= 0):
            return jsonify({'error': 'width and height must be positive integers'}), 400

        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            return jsonify({'error': f'cannot access output_dir: {e}'}), 400

        with recordings_lock:
            existing = recordings.get(camera_id)
            if existing and existing.is_alive():
                return jsonify({'error': 'recording already running for this camera'}), 409

            recorder = RawVideoRecorder(
                camera_id=camera_id,
                rtsp_url=cam['rtsp'],
                output_dir=output_dir,
                filename_prefix=filename_prefix,
                width=width,
                height=height,
            )
            recordings[camera_id] = recorder
            recorder.start()

        return jsonify({
            'started': True,
            'camera_id': camera_id,
            'output_dir': output_dir,
            'width': int(width) if width else None,
            'height': int(height) if height else None,
        }), 201

    @bp.route('/<camera_id>/recording/stop', methods=['POST'])
    def stop_recording(camera_id):
        with recordings_lock:
            recorder = recordings.get(camera_id)
        if recorder is None:
            return jsonify({'error': 'recording not running for this camera'}), 404

        recorder.stop()
        recorder.join(timeout=6.0)

        with recordings_lock:
            if not recorder.is_alive():
                recordings.pop(camera_id, None)

        status = recorder.status()
        if recorder.is_alive():
            return jsonify({'stopping': True, 'status': status}), 202

        return jsonify({'stopped': True, 'status': status})

    return bp
