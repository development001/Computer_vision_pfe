from flask import Blueprint, jsonify, request, Response
import uuid
import cv2
import persistence

def create_cameras_blueprint(cameras, jobs, jobs_lock):
    bp = Blueprint('cameras', __name__, url_prefix='/cameras')

    @bp.route('', methods=['GET'])
    def list_cameras():
        return jsonify({'cameras': cameras})

    @bp.route('', methods=['POST'])
    def add_camera():
        data = request.json or {}
        name = data.get('name') or f'cam-{len(cameras)+1}'
        rtsp = data.get('rtsp')
        if not rtsp:
            return jsonify({'error': 'rtsp field required'}), 400
        cid = str(uuid.uuid4())
        cameras[cid] = {'name': name, 'rtsp': rtsp}
        persistence.save_state(cameras, jobs, jobs_lock)
        return jsonify({'camera_id': cid}), 201

    @bp.route('/<camera_id>/snapshot', methods=['GET'])
    def camera_snapshot(camera_id):
        cam = cameras.get(camera_id)
        if not cam:
            return jsonify({'error': 'unknown camera'}), 404
        rtsp_url = cam['rtsp']
        
        # Get RTSP configuration from request parameters
        width = request.args.get('width', type=int)
        height = request.args.get('height', type=int)
        
        rtsp_kwargs = {}
        if width: rtsp_kwargs['width'] = width
        if height: rtsp_kwargs['height'] = height
        
        # Use a temporary stream to capture a single frame
        from rtsp import RTSPVideoStream
        stream = RTSPVideoStream(rtsp_url, **rtsp_kwargs)
        stream.start()
        
        try:
            # Wait up to 5 seconds for a frame
            frame = stream.read(timeout=5.0)
                
            if frame is None:
                return jsonify({'error': 'failed to grab frame'}), 500
                
            ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                return jsonify({'error': 'failed to encode frame'}), 500
                
            return Response(buf.tobytes(), mimetype='image/jpeg')
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            stream.stop()

    @bp.route('/<camera_id>/mjpeg', methods=['GET'])
    def camera_mjpeg(camera_id):
        cam = cameras.get(camera_id)
        if not cam:
            return 'unknown camera', 404
        rtsp_url = cam['rtsp']
        
        from rtsp import RTSPVideoStream
        
        def generator():
            stream = RTSPVideoStream(rtsp_url)
            stream.start()
            try:
                while True:
                    frame = stream.read(timeout=0.5)
                    if frame is None:
                        if not stream.is_alive():
                            break
                        continue
                    
                    ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if not ok:
                        continue
                        
                    frame_bytes = buf.tobytes()
                    yield (b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            finally:
                stream.stop()

        return Response(generator(), mimetype='multipart/x-mixed-replace; boundary=frame')

    return bp
