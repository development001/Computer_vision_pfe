from flask import Blueprint, jsonify, request
import os
import yaml

def create_trackers_blueprint(trackers_dir):
    bp = Blueprint('trackers', __name__, url_prefix='/trackers')

    @bp.route('', methods=['GET'])
    def list_trackers():
        trackers = []
        try:
            for filename in os.listdir(trackers_dir):
                if filename.endswith('.yml') or filename.endswith('.yaml'):
                    filepath = os.path.join(trackers_dir, filename)
                    with open(filepath, 'r') as f:
                        config = yaml.safe_load(f)
                    trackers.append({
                        'name': filename.rsplit('.', 1)[0],
                        'filename': filename,
                        'config': config
                    })
        except Exception as e:
            print(f"Error loading trackers: {e}")
            return jsonify({'error': 'Failed to load trackers'}), 500
        
        return jsonify(trackers)

    @bp.route('', methods=['POST'])
    def save_tracker():
        data = request.json or {}
        name = data.get('name')
        config = data.get('config')
        
        if not name or not config:
            return jsonify({'error': 'name and config fields required'}), 400
        
        # Validate tracker type
        tracker_type = config.get('tracker_type')
        if tracker_type not in ['botsort', 'bytetrack']:
            return jsonify({'error': 'tracker_type must be botsort or bytetrack'}), 400
        
        # Sanitize filename
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        
        if not safe_name:
            return jsonify({'error': 'invalid tracker name'}), 400
        
        filename = f"{safe_name}.yml"
        filepath = os.path.join(trackers_dir, filename)
        
        # Check if file already exists
        if os.path.exists(filepath):
            return jsonify({'error': 'tracker with this name already exists'}), 409
        
        try:
            with open(filepath, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            return jsonify({'message': 'tracker saved', 'name': safe_name}), 201
        except Exception as e:
            print(f"Error saving tracker: {e}")
            return jsonify({'error': 'Failed to save tracker'}), 500

    @bp.route('/<name>', methods=['DELETE'])
    def delete_tracker(name):
        # Sanitize input
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        
        if not safe_name:
            return jsonify({'error': 'invalid tracker name'}), 400
        
        filename = f"{safe_name}.yml"
        filepath = os.path.join(trackers_dir, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'tracker not found'}), 404
        
        try:
            os.remove(filepath)
            return jsonify({'message': 'tracker deleted', 'name': safe_name})
        except Exception as e:
            print(f"Error deleting tracker: {e}")
            return jsonify({'error': 'Failed to delete tracker'}), 500

    return bp
