import threading
import time
import cv2
from rtsp import RTSPVideoStream
from processor import VideoProcessor

class TrackingWorker(threading.Thread):
    def __init__(self, config):
        super().__init__(daemon=True)
        self.config = config
        self._stop_event = threading.Event()
        self.status = "created"
        self.latest_jpeg = None
        self.stats = {
            'total_unique': 0,
            'class_counts': {},
            'line_counts': {},
        }
        self.processor = None

    def start(self):
        self.status = "starting"
        super().start()

    def run(self):
        try:
            self.processor = VideoProcessor(self.config)
            self.status = "running"
        except Exception as e:
            self.status = f"error: {e}"
            return

        rtsp_cfg = self.config.rtsp_config
        stream = RTSPVideoStream(
            rtsp_url=self.config.rtsp_url,
            width=rtsp_cfg.width,
            height=rtsp_cfg.height,
            fps=rtsp_cfg.fps,
            reconnect_delay=rtsp_cfg.reconnect_delay,
            buffer_size=rtsp_cfg.buffer_size,
            read_timeout=rtsp_cfg.read_timeout,
            cv2_backend=rtsp_cfg.cv2_backend,
        )

        try:
            stream.start()
            while not self._stop_event.is_set():
                im0 = stream.read(timeout=rtsp_cfg.read_timeout)
                if im0 is None:
                    print("No frame received from stream, retrying...")
                    time.sleep(0.2)
                    continue

                annotated_frame = self.processor.process_frame(im0)
                self.stats = self.processor.stats
                ok, jpeg = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    self.latest_jpeg = jpeg.tobytes()

        except Exception as e:
            self.status = f"error: {e}"
        finally:
            try:
                stream.stop()
            except Exception:
                pass
            if self.processor is not None:
                try:
                    self.processor.close()
                except Exception:
                    pass
            if self.status == 'running':
                self.status = 'stopped'

    def stop(self):
        self._stop_event.set()

    def is_running(self):
        return self.status == 'running'
