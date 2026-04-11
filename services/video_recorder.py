import threading
from datetime import datetime
import cv2
import os


class RawVideoRecorder(threading.Thread):
    """Thread-based video recorder for RTSP streams."""
    
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
