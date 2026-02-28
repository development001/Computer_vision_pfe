from flask import Blueprint, jsonify, request
import os
import yaml
from werkzeug.utils import secure_filename
from services.model_optimizer import ModelOptimizer

def create_models_blueprint(models_dir, allowed_extensions, available_models_func):
    bp = Blueprint('models', __name__, url_prefix='/models')

    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

    @bp.route('', methods=['GET'])
    def list_models():
        return jsonify({'models': available_models_func()})

    @bp.route('/upload', methods=['POST'])
    def upload_model():
        if 'file' not in request.files:
            return jsonify({'error': 'no file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'no file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'only .pt and .onnx files allowed'}), 400
        filename = secure_filename(file.filename)
        filepath = os.path.join(models_dir, filename)
        file.save(filepath)
        return jsonify({'message': 'model uploaded', 'filename': filename}), 201

    @bp.route('/optimize', methods=['POST'])
    def optimize_model():
        data = request.json or {}
        source = data.get('source')
        target = (data.get('target') or '').lower()
        imgsz = data.get('imgsz', 640)
        opset = int(data.get('opset', 12))
        dynamic = bool(data.get('dynamic', False))
        half = bool(data.get('half', False))

        if not source:
            return jsonify({'error': 'source field required'}), 400
        if target not in ('onnx', 'tensorrt'):
            return jsonify({'error': 'target must be "onnx" or "tensorrt"'}), 400

        try:
            from services.model_optimizer import ModelOptimizer
        except Exception as e:
            return jsonify({'error': f'optimizer unavailable: {e}'}), 500
        try:
            optimizer = ModelOptimizer(models_dir)
            out_name = optimizer.optimize(source, target, imgsz=imgsz, opset=opset, dynamic=dynamic, half=half)
            return jsonify({'message': 'model optimized', 'filename': out_name, 'format': target}), 200
        except Exception as e:
            return jsonify({'error': f'optimization failed: {e}'}), 500

    return bp
