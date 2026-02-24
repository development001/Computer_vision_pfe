import threading
import time
import cv2
import numpy as np

class RTSPVideoStream(threading.Thread):
    def __init__(self, rtsp_url, width=640, height=640, fps=15, reconnect_delay=3.0, 
                 buffer_size=1, read_timeout=5.0, cv2_backend=None):
        super().__init__(daemon=True)
        self.rtsp_url = rtsp_url
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.reconnect_delay = reconnect_delay
        self.buffer_size = int(buffer_size)
        self.read_timeout = read_timeout
        self.cv2_backend = cv2_backend

        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self.latest_frame = None
        self.is_connected = False
        self._cap = None

    def run(self):
        print(f"Starting RTSP reader for {self.rtsp_url}")
        while not self._stop_event.is_set():
            try:
                if self._cap is None or not self._cap.isOpened():
                    self._connect()

                if not self._cap.isOpened():
                    time.sleep(self.reconnect_delay)
                    continue

                ret, frame = self._cap.read()
                if not ret:
                    print("RTSP frame read failed (stream ended or lost), reconnecting...")
                    self._disconnect()
                    time.sleep(self.reconnect_delay)
                    continue

                # Resize if needed to match requested dimensions
                if frame.shape[0] != self.height or frame.shape[1] != self.width:
                    frame = cv2.resize(frame, (self.width, self.height))

                with self._lock:
                    self.latest_frame = frame.copy()
                    self.is_connected = True
                
            except Exception as e:
                print(f"RTSP loop error: {e}")
                self._disconnect()
                time.sleep(self.reconnect_delay)

        self._disconnect()
        print("RTSP reader thread stopped")

    def _connect(self):
        print(f"Connecting to RTSP: {self.rtsp_url}")
        try:
            # Map string backend to cv2 constant if provided
            backend_const = None
            if self.cv2_backend:
                backend_map = {
                    'FFMPEG': cv2.CAP_FFMPEG,
                    'GSTREAMER': cv2.CAP_GSTREAMER,
                    'DSHOW': cv2.CAP_DSHOW,
                    'MSMF': cv2.CAP_MSMF,
                }
                backend_const = backend_map.get(self.cv2_backend)

            if backend_const is not None:
                self._cap = cv2.VideoCapture(self.rtsp_url, backend_const)
            else:
                self._cap = cv2.VideoCapture(self.rtsp_url)
            
            if self._cap.isOpened():
                # Set buffer size to minimize latency
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
                print(f"RTSP connected: {self.rtsp_url} (buffer_size={self.buffer_size}, backend={self.cv2_backend or 'default'})")
            else:
                print(f"Failed to open RTSP: {self.rtsp_url}")
        except Exception as e:
            print(f"RTSP connection error: {e}")
            self._cap = None

    def _disconnect(self):
        self.is_connected = False
        with self._lock:

            pass
            
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def read(self, timeout=None):
        """
        Returns the latest frame. 
        If timeout is provided, waits up to timeout seconds for a frame to exist.
        """
        start = time.time()
        while timeout is None or (time.time() - start) < timeout:
            with self._lock:
                if self.latest_frame is not None:
                    return self.latest_frame.copy()
            time.sleep(0.01)
        return None

    def stop(self):
        self._stop_event.set()
    
    def is_open(self):
        return self.is_connected
