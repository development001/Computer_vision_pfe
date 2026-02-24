import threading
import time
import cv2
import numpy as np
import os
from rtsp import RTSPVideoStream
from processor import VideoProcessor

class TrackingWorker(threading.Thread):
    def __init__(self, config):
        super().__init__(daemon=True)
        self.config = config
        self.rtsp_url = config.rtsp_url
        
        # RTSP configuration parameters
        self.rtsp_config = {
            'width': config.rtsp_config.width,
            'height': config.rtsp_config.height,
            'fps': config.rtsp_config.fps,
            'reconnect_delay': config.rtsp_config.reconnect_delay,
            'buffer_size': config.rtsp_config.buffer_size,
            'read_timeout': config.rtsp_config.read_timeout,
            'cv2_backend': config.rtsp_config.cv2_backend
        }
        
        self._stop_event = threading.Event()
        self.status = "created"
        self.latest_jpeg = None
        self.processor = None

    def start(self):
        self.status = "starting"
        super().start()

    def run(self):
        try:
            self.processor = VideoProcessor(self.config)
            self.status = "running"
        except Exception as e:
            self.status = f"error: failed to init processor: {e}"
            print(f"Error: {self.status}")
            return

        stream = self._init_stream()
        if not stream:
            return

        try:
            while not self._stop_event.is_set():
                frame = stream.read(timeout=self.rtsp_config['read_timeout'])
                if frame is None:
                    print("Warning: No frame received from stream, retrying...")
                    time.sleep(0.2)
                    continue

                processed_frame = self.processor.process_frame(frame)
                self._update_latest_jpeg(processed_frame)

        except Exception as e:
            self.status = f"error: {e}"
            print(f"Error: Worker loop error: {e}")
        finally:
            self._cleanup(stream)

    def _init_stream(self):
        try:
            stream = RTSPVideoStream(self.rtsp_url, **self.rtsp_config)
            stream.start()
            
            # Allow some time for connection
            time.sleep(0.5)
            if not stream.is_open():
                print(f"Info: RTSP stream connecting... {self.rtsp_url}")
            return stream
        except Exception as e:
            self.status = f"error: failed to start stream: {e}"
            print(f"Error: {self.status}")
            return None

    def _update_latest_jpeg(self, frame):
        try:
            _, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            self.latest_jpeg = jpeg.tobytes()
        except Exception:
            pass

    def _cleanup(self, stream):
        
        if self.status == 'running':
            self.status = 'stopped'
        if stream:
            try:
                stream.stop()
            except Exception:
                pass
        
        if self.processor:
            self.processor.close()

        cv2.destroyAllWindows()

    def stop(self):
        self._stop_event.set()

    def is_running(self):
        
        return self.status == 'running'
