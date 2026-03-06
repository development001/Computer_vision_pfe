import mimetypes
import re

from flask import Blueprint, Response, jsonify, request


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _parse_prompt_terms(prompt):
    if prompt is None:
        return []
    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string")
    parts = [x.strip() for x in re.split(r"[\n,]+", prompt) if x.strip()]
    return parts


def _parse_threshold(value, name, default):
    if value is None or value == "":
        return default
    try:
        out = float(value)
    except Exception as exc:
        raise ValueError(f"{name} must be a number") from exc
    if out < 0.0 or out > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return out


def create_training_blueprint(store, runner, autodistill_service=None):
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

    @bp.route("/datasets/<dataset_id>/images/from-video", methods=["POST"])
    def upload_images_from_video(dataset_id):
        video = request.files.get("video") or request.files.get("file")
        every_nth_frame = request.form.get("every_nth_frame", default=1, type=int)
        if every_nth_frame is None or every_nth_frame < 1:
            return jsonify({"error": "every_nth_frame must be >= 1"}), 400

        try:
            result = store.add_images_from_video(dataset_id, video, every_nth_frame=every_nth_frame)
            if result.get("extracted_count", 0) <= 0:
                return jsonify({"error": "no frames extracted from video"}), 400
            return jsonify(result), 201
        except KeyError:
            return jsonify({"error": "dataset not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

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

    @bp.route("/autodistill/status", methods=["GET"])
    def autodistill_status():
        if autodistill_service is None:
            return jsonify({"available": False, "error": "autodistill service is disabled"})
        return jsonify(autodistill_service.availability())

    @bp.route("/datasets/<dataset_id>/annotation-versions/<version_id>/autodistill", methods=["POST"])
    def run_autodistill(dataset_id, version_id):
        if autodistill_service is None:
            return jsonify({"error": "autodistill service is disabled"}), 503

        data = request.json or {}
        try:
            prompt_terms = _parse_prompt_terms(data.get("prompt"))
            box_threshold = _parse_threshold(data.get("box_threshold"), "box_threshold", default=0.35)
            text_threshold = _parse_threshold(data.get("text_threshold"), "text_threshold", default=0.25)
            replace_existing = _to_bool(data.get("replace_existing"), default=False)
            provider = (data.get("provider") or "dino").strip().lower()
            if provider not in {"dino", "grounded_sam", "grounded_sam2", "auto"}:
                raise ValueError("provider must be one of: dino, grounded_sam, grounded_sam2, auto")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        image_ids_input = data.get("image_ids")
        if image_ids_input is not None and not isinstance(image_ids_input, list):
            return jsonify({"error": "image_ids must be a list of image ids"}), 400

        try:
            material = store.get_training_material(dataset_id, version_id)
            classes = material["classes"]
            if not classes:
                return jsonify({"error": "no classes available. create classes first"}), 400

            class_lookup = {c["name"].strip().lower(): c for c in classes}
            selected_classes = []
            missing_terms = []

            if prompt_terms:
                used_ids = set()
                for term in prompt_terms:
                    cls = class_lookup.get(term.lower())
                    if not cls:
                        missing_terms.append(term)
                        continue
                    if cls["id"] in used_ids:
                        continue
                    used_ids.add(cls["id"])
                    selected_classes.append(cls)
            else:
                selected_classes = list(classes)

            if missing_terms:
                return jsonify({
                    "error": "prompt terms must match existing class names",
                    "missing_terms": missing_terms,
                }), 400
            if not selected_classes:
                return jsonify({"error": "prompt did not resolve to any class"}), 400

            images = material["images"]
            image_by_id = {img["id"]: img for img in images}

            if image_ids_input is not None:
                selected_images = []
                seen = set()
                missing_images = []
                for image_id in image_ids_input:
                    if image_id in seen:
                        continue
                    seen.add(image_id)
                    img = image_by_id.get(image_id)
                    if not img:
                        missing_images.append(image_id)
                        continue
                    selected_images.append(img)
                if missing_images:
                    return jsonify({
                        "error": "some image_ids do not exist in this dataset",
                        "missing_image_ids": missing_images,
                    }), 400
            else:
                selected_images = images

            image_items = []
            for image in selected_images:
                image_items.append({
                    "id": image["id"],
                    "path": store.get_image_abs_path(dataset_id, image["id"]),
                })

            ontology_map = {cls["name"]: cls["name"] for cls in selected_classes}
            ontology_class_ids = [int(cls["id"]) for cls in selected_classes]

            result = autodistill_service.run(
                image_items=image_items,
                ontology_map=ontology_map,
                ontology_class_ids=ontology_class_ids,
                box_threshold=box_threshold,
                text_threshold=text_threshold,
                provider=provider,
            )

            selected_image_ids = [img["id"] for img in selected_images]
            if replace_existing:
                final_annotations_by_image = {
                    image_id: result["annotations_by_image"].get(image_id, [])
                    for image_id in selected_image_ids
                }
            else:
                existing_by_image = store.get_annotations_map(
                    dataset_id, version_id, selected_image_ids
                )
                final_annotations_by_image = {}
                for image_id in selected_image_ids:
                    existing = existing_by_image.get(image_id, [])
                    generated = result["annotations_by_image"].get(image_id, [])
                    final_annotations_by_image[image_id] = existing + generated

            save_result = store.save_annotations_bulk(
                dataset_id, version_id, final_annotations_by_image
            )

            return jsonify({
                "processed_images": result["processed_images"],
                "labeled_images": result["labeled_images"],
                "predicted_boxes": result["predicted_boxes"],
                "saved_images": save_result["saved_images"],
                "saved_total_boxes": save_result["saved_boxes"],
                "replace_existing": replace_existing,
                "provider": result.get("provider"),
                "errors": result["errors"],
            })
        except KeyError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 503
        except Exception as e:
            return jsonify({"error": f"autodistill failed unexpectedly: {e}"}), 500

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
