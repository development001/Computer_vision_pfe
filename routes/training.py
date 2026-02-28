import mimetypes

from flask import Blueprint, Response, jsonify, request


def create_training_blueprint(store, runner):
    bp = Blueprint("training", __name__, url_prefix="/training")

    @bp.route("/datasets", methods=["GET"])
    def list_datasets():
        return jsonify({"datasets": store.list_datasets()})

    @bp.route("/datasets", methods=["POST"])
    def create_dataset():
        data = request.json or {}
        try:
            dataset = store.create_dataset(
                name=data.get("name", ""),
                description=data.get("description", ""),
            )
            return jsonify(dataset), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/datasets/<dataset_id>", methods=["GET"])
    def get_dataset(dataset_id):
        try:
            return jsonify(store.get_dataset(dataset_id))
        except KeyError:
            return jsonify({"error": "dataset not found"}), 404

    @bp.route("/datasets/<dataset_id>", methods=["PATCH"])
    def update_dataset(dataset_id):
        data = request.json or {}
        try:
            dataset = store.update_dataset(
                dataset_id,
                name=data.get("name") if "name" in data else None,
                description=data.get("description") if "description" in data else None,
            )
            return jsonify(dataset)
        except KeyError:
            return jsonify({"error": "dataset not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/datasets/<dataset_id>", methods=["DELETE"])
    def delete_dataset(dataset_id):
        try:
            store.delete_dataset(dataset_id)
            return jsonify({"deleted": dataset_id})
        except KeyError:
            return jsonify({"error": "dataset not found"}), 404

    @bp.route("/datasets/<dataset_id>/images", methods=["POST"])
    def upload_images(dataset_id):
        files = request.files.getlist("files")
        if not files and "file" in request.files:
            files = [request.files["file"]]
        try:
            saved = store.add_images(dataset_id, files)
            if not saved:
                return jsonify({"error": "no valid image files provided"}), 400
            return jsonify({"uploaded": saved}), 201
        except KeyError:
            return jsonify({"error": "dataset not found"}), 404

    @bp.route("/datasets/<dataset_id>/images", methods=["GET"])
    def list_images(dataset_id):
        try:
            images = store.list_images(dataset_id)
            for image in images:
                image["url"] = f"/training/datasets/{dataset_id}/images/{image['id']}/file"
            return jsonify({"images": images})
        except KeyError:
            return jsonify({"error": "dataset not found"}), 404

    @bp.route("/datasets/<dataset_id>/images/<image_id>", methods=["DELETE"])
    def delete_image(dataset_id, image_id):
        try:
            store.delete_image(dataset_id, image_id)
            return jsonify({"deleted": image_id})
        except KeyError as e:
            return jsonify({"error": str(e)}), 404

    @bp.route("/datasets/<dataset_id>/images/<image_id>/file", methods=["GET"])
    def get_image_file(dataset_id, image_id):
        try:
            path = store.get_image_abs_path(dataset_id, image_id)
        except KeyError:
            return jsonify({"error": "image not found"}), 404
        try:
            with open(path, "rb") as f:
                data = f.read()
            mimetype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            return Response(data, mimetype=mimetype)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/datasets/<dataset_id>/classes", methods=["GET"])
    def list_classes(dataset_id):
        try:
            return jsonify({"classes": store.list_classes(dataset_id)})
        except KeyError:
            return jsonify({"error": "dataset not found"}), 404

    @bp.route("/datasets/<dataset_id>/classes", methods=["POST"])
    def add_class(dataset_id):
        data = request.json or {}
        try:
            cls = store.add_class(
                dataset_id,
                name=data.get("name", ""),
                color=data.get("color", ""),
                class_id=data.get("id"),
            )
            return jsonify(cls), 201
        except KeyError:
            return jsonify({"error": "dataset not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/datasets/<dataset_id>/classes/<int:class_id>", methods=["PATCH"])
    def update_class(dataset_id, class_id):
        data = request.json or {}
        try:
            cls = store.update_class(
                dataset_id,
                class_id,
                name=data.get("name") if "name" in data else None,
                color=data.get("color") if "color" in data else None,
            )
            return jsonify(cls)
        except KeyError:
            return jsonify({"error": "class not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/datasets/<dataset_id>/classes/<int:class_id>", methods=["DELETE"])
    def delete_class(dataset_id, class_id):
        try:
            store.delete_class(dataset_id, class_id)
            return jsonify({"deleted": class_id})
        except KeyError:
            return jsonify({"error": "class not found"}), 404
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 409

    @bp.route("/datasets/<dataset_id>/annotation-versions", methods=["GET"])
    def list_versions(dataset_id):
        try:
            return jsonify({"annotation_versions": store.list_annotation_versions(dataset_id)})
        except KeyError:
            return jsonify({"error": "dataset not found"}), 404

    @bp.route("/datasets/<dataset_id>/annotation-versions", methods=["POST"])
    def create_version(dataset_id):
        data = request.json or {}
        try:
            version = store.create_annotation_version(
                dataset_id,
                name=data.get("name", ""),
                source_version_id=data.get("source_version_id"),
            )
            return jsonify(version), 201
        except KeyError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/datasets/<dataset_id>/annotation-versions/<version_id>", methods=["PATCH"])
    def update_version(dataset_id, version_id):
        data = request.json or {}
        try:
            version = store.update_annotation_version(dataset_id, version_id, data.get("name", ""))
            return jsonify(version)
        except KeyError:
            return jsonify({"error": "annotation version not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/datasets/<dataset_id>/annotation-versions/<version_id>", methods=["DELETE"])
    def delete_version(dataset_id, version_id):
        try:
            store.delete_annotation_version(dataset_id, version_id)
            return jsonify({"deleted": version_id})
        except KeyError:
            return jsonify({"error": "annotation version not found"}), 404

    @bp.route("/datasets/<dataset_id>/annotation-versions/<version_id>/annotations/<image_id>", methods=["GET"])
    def get_annotations(dataset_id, version_id, image_id):
        try:
            return jsonify(
                {"annotations": store.get_annotations(dataset_id, version_id, image_id)}
            )
        except KeyError as e:
            return jsonify({"error": str(e)}), 404

    @bp.route("/datasets/<dataset_id>/annotation-versions/<version_id>/annotations/<image_id>", methods=["PUT"])
    def save_annotations(dataset_id, version_id, image_id):
        data = request.json or []
        if not isinstance(data, list):
            return jsonify({"error": "annotations payload must be a list"}), 400
        try:
            result = store.save_annotations(dataset_id, version_id, image_id, data)
            return jsonify(result)
        except KeyError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/datasets/<dataset_id>/annotation-versions/<version_id>/stats", methods=["GET"])
    def stats(dataset_id, version_id):
        try:
            return jsonify(store.annotation_stats(dataset_id, version_id))
        except KeyError as e:
            return jsonify({"error": str(e)}), 404

    @bp.route("/jobs/start", methods=["POST"])
    def start_training():
        data = request.json or {}
        try:
            job = runner.start_job(data)
            return jsonify(job), 201
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 409
        except (ValueError, KeyError) as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/jobs", methods=["GET"])
    def list_jobs():
        return jsonify({"jobs": runner.list_jobs(), "active_job_id": store.get_active_job_id()})

    @bp.route("/jobs/<job_id>", methods=["GET"])
    def get_job(job_id):
        try:
            job = runner.get_job(job_id)
            return jsonify(job)
        except KeyError:
            return jsonify({"error": "job not found"}), 404

    @bp.route("/jobs/<job_id>/logs", methods=["GET"])
    def get_logs(job_id):
        offset = request.args.get("offset", default=0, type=int)
        try:
            logs = runner.get_logs(job_id, offset=offset)
            return jsonify(logs)
        except KeyError:
            return jsonify({"error": "job not found"}), 404

    @bp.route("/jobs/<job_id>/stop", methods=["POST"])
    def stop_job(job_id):
        try:
            job = runner.stop_job(job_id)
            return jsonify(job)
        except KeyError:
            return jsonify({"error": "job not found"}), 404

    return bp
