import numpy as np
from datetime import datetime

class DetectedObject:
    def __init__(self, class_name: str, object_id: int, detection_time: datetime, location: list, image: np.ndarray, inOrOut: str, confidence: float):
        self.class_name = class_name
        self.object_id = object_id
        self.detection_time = detection_time
        self.location = location  # [x, y, w, h]
        self.image = image
        self.inOrOut = inOrOut
        self.confidence = confidence

    def __repr__(self):
        print(f"DetectedObject(class_name={self.class_name}, object_id={self.object_id}, detection_time={self.detection_time}, location={self.location}, inOrOut={self.inOrOut}, confidence={self.confidence})")