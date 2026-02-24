import os
from werkzeug.utils import secure_filename
from ultralytics import YOLO

class ModelOptimizer:
    def __init__(self, models_dir):
        self.models_dir = models_dir

    def optimize(self, source, target, imgsz, opset=12, dynamic=False, half=False):
        src_path = os.path.join(self.models_dir, secure_filename(source))
        if not os.path.exists(src_path):
            raise FileNotFoundError('source model not found')

        model = YOLO(src_path)
        if target == 'onnx':
            out_path = model.export(format='onnx', imgsz=imgsz, opset=opset, dynamic=dynamic)
        elif target == 'tensorrt':
            try:
                import tensorrt  # noqa: F401
            except Exception:
                raise RuntimeError('TensorRT not installed. Install NVIDIA TensorRT or choose ONNX/OpenVINO.')
            out_path = model.export(format='engine', imgsz=imgsz, half=half)
        else:
            raise ValueError('unsupported target')

        if not isinstance(out_path, str) or not os.path.exists(out_path):
            raise RuntimeError('export did not produce a file')

        out_name = os.path.basename(out_path)
        dest_path = os.path.join(self.models_dir, out_name)
        if os.path.abspath(os.path.dirname(out_path)) != os.path.abspath(self.models_dir):
            import shutil
            try:
                shutil.move(out_path, dest_path)
            except Exception:
                shutil.copy2(out_path, dest_path)
        else:
            dest_path = out_path

        return os.path.basename(dest_path)
