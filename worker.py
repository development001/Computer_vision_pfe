import threading
import time
import cv2
import numpy as np
import os
from ultralytics import YOLO
from rtsp import RTSPVideoStream

class TrackingWorker(threading.Thread):
    def __init__(self, rtsp_url, model_name, imgsz=640, classes_to_count=None, 
                 rtsp_width=640, rtsp_height=640, rtsp_fps=15, rtsp_reconnect_delay=3.0,
                 rtsp_buffer_size=1, rtsp_read_timeout=5.0, rtsp_cv2_backend=None):
        super().__init__(daemon=True)
        self.rtsp = rtsp_url
        self.model_name = model_name
        try:
            self.imgsz = int(imgsz)
        except Exception:
            self.imgsz = 640
        
        # RTSP configuration parameters
        self.rtsp_width = int(rtsp_width)
        self.rtsp_height = int(rtsp_height)
        self.rtsp_fps = int(rtsp_fps)
        self.rtsp_reconnect_delay = float(rtsp_reconnect_delay)
        self.rtsp_buffer_size = int(rtsp_buffer_size)
        self.rtsp_read_timeout = float(rtsp_read_timeout)
        self.rtsp_cv2_backend = rtsp_cv2_backend
        
        # Default to counting all classes if none specified
        self.classes_to_count = classes_to_count or None
        
        self._debug_frame_count = 0
        self._stop_event = threading.Event()
        self.status = "created"
        self.latest_jpeg = None
        self.stats = {
            'total_unique': 0,
            'class_counts': {},  # class_name -> count
        }
        self.seen_ids = {}
        self.last_centroid = {}
        self.line_y = None
        self._cap = None
        self.model = None
        self.counter = None
        self.line_points = None  # Will be set dynamically

    def start(self):
        self.status = "starting"
        super().start()

    def run(self):

        self.init_model()
        
        try:
           
            stream = RTSPVideoStream(
                self.rtsp, 
                width=self.rtsp_width, 
                height=self.rtsp_height, 
                fps=self.rtsp_fps, 
                reconnect_delay=self.rtsp_reconnect_delay,
                buffer_size=self.rtsp_buffer_size,
                read_timeout=self.rtsp_read_timeout,
                cv2_backend=self.rtsp_cv2_backend
            )
            stream.start()
            
            # Wait briefly for connection, but don't fail immediately if it takes longer
            time.sleep(0.5)
            if not stream.is_open():
                print(f"RTSP stream connecting... {self.rtsp}")

            while not self._stop_event.is_set():
                im0 = stream.read(timeout=5.0)
                if im0 is None:
                    print("No frame received from stream, retrying...")
                    time.sleep(0.2)
                    continue


                # ---------------------------
                # 1) Run YOLO with tracking to get raw per-frame IDs & class indices
                # ---------------------------
                try:
                    # Added tracker config and lowered thresholds to improve ID assignment
                    # stream=True returns a generator, so we need to iterate through results
                    track_generator = self.model.track(
                        im0, 
                        persist=True, 
                        verbose=False,
                        tracker="bytetrack.yaml",  # Explicitly use ByteTrack (often better than BoT-SORT for stability)
                        conf=0.4,                 # Ensure confidence isn't filtering too aggressively
                        iou=0.5,
                        track_buffer=60,  # increase if objects re-appear after short occlusions
                        stream=True                # Returns generator for streaming results
                    )
                    
                    # Prepare per-frame tracked lists
                    tracked_frame_ids = []
                    tracked_frame_class_idxs = []
                    tracked_frame_class_names = []
                    
                    # Iterate through the generator results
                    for r in track_generator:
                        boxes = getattr(r, "boxes", None)
                        if boxes is not None:
                            # boxes.id and boxes.cls are tensors in Ultralytics results
                            print(f"Boxes: {boxes}")
                            try:
                                ids = boxes.id.cpu().numpy().astype(int).tolist() if hasattr(boxes, "id") and boxes.id is not None else []
                            except Exception:
                                ids = []
                            try:
                                cls_idxs = boxes.cls.cpu().numpy().astype(int).tolist() if hasattr(boxes, "cls") and boxes.cls is not None else []
                            except Exception:
                                cls_idxs = []

                            if len(cls_idxs) > 0 and len(ids) == 0:
                                print(f"WARNING: {len(cls_idxs)} objects detected but NO IDs assigned. Tracking might be failing or initializing.")
                            
                            if len(ids) > 0:
                                print(f"Tracking IDs: {ids}")

                            # map ids -> class names and update persistent mapping / stats
                            for tid, cid in zip(ids, cls_idxs):
                                # class name from model.names (dict idx->name)
                                cname = self.model.names.get(int(cid), str(cid)) if hasattr(self.model, "names") else str(cid)

                                tracked_frame_ids.append(int(tid))
                                tracked_frame_class_idxs.append(int(cid))
                                tracked_frame_class_names.append(cname)

                                # add to global seen mapping and update stats only once per unique id
                                if int(tid) not in self.seen_ids:
                                    self.seen_ids[int(tid)] = cname
                                    # update total unique and per-class counters
                                    self.stats['total_unique'] = len(self.seen_ids)
                                    self.stats['class_counts'][cname] = self.stats['class_counts'].get(cname, 0) + 1
                                    print(f"New object detected: ID {tid} ({cname})")
                        
                        # Use self.stats['class_counts'] as the official counts
                        class_counts = self.stats['class_counts']
                        print(f"Class counts: {class_counts}")
                        
                        # Use this result for annotation
                        annotated_frame = r.plot()
                        break  # We only need one result per frame
                        
                except Exception as e:
                    # fallback to running the counter only (shouldn't normally happen)
                    print("Model track() failed:", e)
                    class_counts = self.stats['class_counts']
                    annotated_frame = im0.copy()

                # print class_counts on the frame
                y_offset = 30
                for cname, count in class_counts.items():
                    text = f"{cname}: {count}"
                    # Draw black background for text readability
                    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
                    cv2.rectangle(annotated_frame, (10, y_offset - h - 5), (10 + w, y_offset + 5), (0, 0, 0), -1)
                    cv2.putText(annotated_frame, text, (10, y_offset),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    y_offset += 35
                
                # encode and publish
                _, jpeg = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                self.latest_jpeg = jpeg.tobytes()

            # stop the background reader and cleanup
            try:
                stream.stop()
            except Exception:
                pass
            cv2.destroyAllWindows()

        except Exception as e:
            self.status = f"error: {e}"
        finally:
            if self.status == 'running':
                self.status = 'stopped'


    def stop(self):
        self._stop_event.set()

    def is_running(self):
        return self.status == 'running'
    def init_model(self):
        try:
            model_path = os.path.join(os.path.dirname(__file__), 'models', self.model_name)
            self.model = YOLO(model_path)
        except Exception as e:
            self.status = f"error: failed to load model: {e}"
            return

        self.status = "running"
