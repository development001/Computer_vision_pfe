import threading
import time
import cv2
import numpy as np
import os
from ultralytics import YOLO, solutions
from rtsp import RTSPVideoStream

class TrackingWorker(threading.Thread):
    def __init__(self, rtsp_url, model_name, imgsz=640, classes_to_count=None):
        super().__init__(daemon=True)
        self.rtsp = rtsp_url
        self.model_name = model_name
        try:
            self.imgsz = int(imgsz)
        except Exception:
            self.imgsz = 640
        
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
            # Use a threaded RTSP reader that auto-reconnects to avoid long-run disconnects
            stream = RTSPVideoStream( rtsp_url=self.rtsp, width=self.imgsz, height=self.imgsz, fps=15 )
            stream.start()

            region_points = [(20, 400), (1080, 400)]  # simple static line (start,end)
            counter = solutions.ObjectCounter(show=False, region=region_points, model=self.model, verbose=False)

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
                    tracks = self.model.track(im0, persist=True, verbose=False)
                except Exception as e:
                    # fallback to running the counter only (shouldn't normally happen)
                    print("Model track() failed:", e)
                    tracks = []

                # Prepare per-frame tracked lists
                tracked_frame_ids = []
                tracked_frame_class_idxs = []
                tracked_frame_class_names = []

                if tracks:
                    r = tracks[0]  # usually single result for the frame/stream
                    boxes = getattr(r, "boxes", None)
                    if boxes is not None:
                        # boxes.id and boxes.cls are tensors in Ultralytics results
                        try:
                            ids = boxes.id.cpu().numpy().astype(int).tolist() if hasattr(boxes, "id") and boxes.id is not None else []
                        except Exception:
                            ids = []
                        try:
                            cls_idxs = boxes.cls.cpu().numpy().astype(int).tolist() if hasattr(boxes, "cls") and boxes.cls is not None else []
                        except Exception:
                            cls_idxs = []

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

                # ---------------------------
                # 2) Update ObjectCounter internal state using the produced tracks
                #    (keeps the ObjectCounter behavior you already had)
                # ---------------------------
                try:
                    # counter.start_counting expects the frame and the tracked results
                    counter.start_counting(im0, tracks)
                except Exception as e:
                    print("Counter start_counting failed:", e)
                    

                # get classwise counts from the counter (optional, mirror of counter state)
                try:
                    class_counts = counter.classwise_counts
                except Exception:
                    class_counts = {}

                # debug / visibility: per-frame and aggregated information
                print("Frame tracked IDs:", tracked_frame_ids)
                print("Frame tracked class idxs:", tracked_frame_class_idxs)
                print("Frame tracked class names:", tracked_frame_class_names)
                print("Mapped IDs -> class:", self.seen_ids)
                print("Counter classwise_counts:", class_counts)
                print("Stats (total_unique):", self.stats['total_unique'])

                # ---------------------------
                # 3) Annotate frame for publishing
                # ---------------------------
                annotated_frame = im0
                # print class_counts on the frame
                y_offset = 30
                for cname, count in class_counts.items():
                    cv2.putText(annotated_frame, f"{cname}: {count}", (10, y_offset),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    y_offset += 30
                # prefer the YOLO tracks' plot (avoids double detect if track.plot exists)
                try:
                    if tracks:
                        annotated_frame = tracks[0].plot()
                except Exception:
                    print("Track plot failed, using raw frame for annotation.")
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
