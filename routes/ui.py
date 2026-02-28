from flask import Blueprint, send_from_directory, jsonify
import os

def create_ui_blueprint(static_dir):
    bp = Blueprint('ui', __name__)

    @bp.route('/')
    def index():
        return send_from_directory(static_dir, 'index.html')

    @bp.route('/ui/<path:name>')
    def ui_pages(name):
        base = name[:-5] if name.endswith('.html') else name
        nested = os.path.join(base, f"{os.path.basename(base)}.html")
        nested_path = os.path.join(static_dir, nested)
        if os.path.exists(nested_path):
            subdir = os.path.join(static_dir, base)
            return send_from_directory(subdir, f"{os.path.basename(base)}.html")
        candidate = name if name.endswith('.html') else f"{name}.html"
        root_path = os.path.join(static_dir, candidate)
        if os.path.exists(root_path):
            return send_from_directory(static_dir, candidate)
        return jsonify({'error': 'page not found'}), 404
        
    return bp
