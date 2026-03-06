import json
import os
import random
import shutil
import threading
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import cv2
from werkzeug.utils import secure_filename


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrainingStore:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.datasets_dir = os.path.join(base_dir, "datasets")
        self.jobs_dir = os.path.join(base_dir, "jobs")
        self.registry_path = os.path.join(base_dir, "registry.json")
        self._lock = threading.RLock()

        os.makedirs(self.datasets_dir, exist_ok=True)
        os.makedirs(self.jobs_dir, exist_ok=True)
        self._ensure_registry()

    def _ensure_registry(self) -> None:
        with self._lock:
            if not os.path.exists(self.registry_path):
                self._save_registry({"datasets": {}, "jobs": {}, "active_job_id": None})
                return
            data = self._load_registry()
            changed = False
            if "datasets" not in data:
                data["datasets"] = {}
                changed = True
            if "jobs" not in data:
                data["jobs"] = {}
                changed = True
            if "active_job_id" not in data:
                data["active_job_id"] = None
                changed = True
            if changed:
                self._save_registry(data)

    def _load_registry(self) -> Dict[str, Any]:
        with open(self.registry_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_registry(self, data: Dict[str, Any]) -> None:
        tmp = f"{self.registry_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.registry_path)

    def _dataset_dir(self, dataset_id: str) -> str:
        return os.path.join(self.datasets_dir, dataset_id)

    def _dataset_images_dir(self, dataset_id: str) -> str:
        return os.path.join(self._dataset_dir(dataset_id), "images")

    def _dataset_versions_dir(self, dataset_id: str) -> str:
        return os.path.join(self._dataset_dir(dataset_id), "annotation_versions")

    def _version_labels_dir(self, dataset_id: str, version_id: str) -> str:
        return os.path.join(self._dataset_versions_dir(dataset_id), version_id, "labels")

    def _require_dataset(self, data: Dict[str, Any], dataset_id: str) -> Dict[str, Any]:
        dataset = data["datasets"].get(dataset_id)
        if not dataset:
            raise KeyError("dataset not found")
        return dataset

    def _require_version(self, dataset: Dict[str, Any], version_id: str) -> Dict[str, Any]:
        version = dataset["annotation_versions"].get(version_id)
        if not version:
            raise KeyError("annotation version not found")
        return version

    def list_datasets(self) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._load_registry()
            out = []
            for dataset in data["datasets"].values():
                out.append({
                    "id": dataset["id"],
                    "name": dataset["name"],
                    "description": dataset.get("description", ""),
                    "created_at": dataset["created_at"],
                    "updated_at": dataset["updated_at"],
                    "image_count": len(dataset.get("images", {})),
                    "class_count": len(dataset.get("classes", [])),
                    "annotation_version_count": len(dataset.get("annotation_versions", {})),
                })
            out.sort(key=lambda x: x["created_at"], reverse=True)
            return out

    def create_dataset(self, name: str, description: str = "") -> Dict[str, Any]:
        if not name or not str(name).strip():
            raise ValueError("name is required")

        with self._lock:
            data = self._load_registry()
            dataset_id = str(uuid.uuid4())
            now = _utc_now()
            dataset = {
                "id": dataset_id,
                "name": str(name).strip(),
                "description": description or "",
                "created_at": now,
                "updated_at": now,
                "images": {},
                "classes": [],
                "annotation_versions": {},
            }
            data["datasets"][dataset_id] = dataset
            os.makedirs(self._dataset_images_dir(dataset_id), exist_ok=True)
            os.makedirs(self._dataset_versions_dir(dataset_id), exist_ok=True)
            self._save_registry(data)
            return dataset

    def get_dataset(self, dataset_id: str) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            return dataset

    def update_dataset(self, dataset_id: str, name: Optional[str], description: Optional[str]) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            if name is not None:
                if not str(name).strip():
                    raise ValueError("name cannot be empty")
                dataset["name"] = str(name).strip()
            if description is not None:
                dataset["description"] = description
            dataset["updated_at"] = _utc_now()
            self._save_registry(data)
            return dataset

    def delete_dataset(self, dataset_id: str) -> None:
        with self._lock:
            data = self._load_registry()
            self._require_dataset(data, dataset_id)
            del data["datasets"][dataset_id]
            self._save_registry(data)
            shutil.rmtree(self._dataset_dir(dataset_id), ignore_errors=True)

    def add_images(self, dataset_id: str, files) -> List[Dict[str, Any]]:
        saved = []
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            images_dir = self._dataset_images_dir(dataset_id)
            os.makedirs(images_dir, exist_ok=True)

            for file in files:
                if not file or not file.filename:
                    continue
                secure = secure_filename(file.filename)
                _, ext = os.path.splitext(secure)
                ext = ext.lower()
                if ext not in ALLOWED_IMAGE_EXTENSIONS:
                    continue
                image_id = str(uuid.uuid4())
                filename = f"{image_id}{ext}"
                abs_path = os.path.join(images_dir, filename)
                file.save(abs_path)
                img = {
                    "id": image_id,
                    "filename": filename,
                    "original_name": secure,
                    "uploaded_at": _utc_now(),
                }
                dataset["images"][image_id] = img
                saved.append(img)

            dataset["updated_at"] = _utc_now()
            self._save_registry(data)
        return saved

    def add_images_from_video(self, dataset_id: str, video_file, every_nth_frame: int = 1) -> Dict[str, Any]:
        if video_file is None or not getattr(video_file, "filename", None):
            raise ValueError("video file is required")
        if every_nth_frame < 1:
            raise ValueError("every_nth_frame must be >= 1")

        secure = secure_filename(video_file.filename)
        _, ext = os.path.splitext(secure)
        ext = ext.lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            raise ValueError("unsupported video format")

        temp_path = None
        extracted = []
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                temp_path = tmp.name
            video_file.save(temp_path)

            cap = cv2.VideoCapture(temp_path)
            if not cap.isOpened():
                raise ValueError("failed to open uploaded video")

            try:
                frame_idx = 0
                saved_idx = 0
                with self._lock:
                    data = self._load_registry()
                    dataset = self._require_dataset(data, dataset_id)
                    images_dir = self._dataset_images_dir(dataset_id)
                    os.makedirs(images_dir, exist_ok=True)

                    while True:
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            break

                        if frame_idx % every_nth_frame == 0:
                            image_id = str(uuid.uuid4())
                            filename = f"{image_id}.jpg"
                            abs_path = os.path.join(images_dir, filename)
                            ok = cv2.imwrite(abs_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
                            if ok:
                                item = {
                                    "id": image_id,
                                    "filename": filename,
                                    "original_name": f"{os.path.splitext(secure)[0]}_frame_{frame_idx:06d}.jpg",
                                    "uploaded_at": _utc_now(),
                                }
                                dataset["images"][image_id] = item
                                extracted.append(item)
                                saved_idx += 1
                        frame_idx += 1

                    dataset["updated_at"] = _utc_now()
                    self._save_registry(data)

                return {
                    "extracted_count": saved_idx,
                    "every_nth_frame": every_nth_frame,
                    "video_name": secure,
                    "images": extracted,
                }
            finally:
                cap.release()
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except FileNotFoundError:
                    pass

    def list_images(self, dataset_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            images = list(dataset.get("images", {}).values())
            images.sort(key=lambda x: x["uploaded_at"], reverse=True)
            return images

    def get_image_abs_path(self, dataset_id: str, image_id: str) -> str:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            image = dataset.get("images", {}).get(image_id)
            if not image:
                raise KeyError("image not found")
            return os.path.join(self._dataset_images_dir(dataset_id), image["filename"])

    def delete_image(self, dataset_id: str, image_id: str) -> None:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            image = dataset.get("images", {}).get(image_id)
            if not image:
                raise KeyError("image not found")

            img_path = os.path.join(self._dataset_images_dir(dataset_id), image["filename"])
            try:
                os.remove(img_path)
            except FileNotFoundError:
                pass

            for version_id in dataset.get("annotation_versions", {}).keys():
                label_file = os.path.join(self._version_labels_dir(dataset_id, version_id), f"{image_id}.txt")
                try:
                    os.remove(label_file)
                except FileNotFoundError:
                    pass

            del dataset["images"][image_id]
            dataset["updated_at"] = _utc_now()
            self._save_registry(data)

    def list_classes(self, dataset_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            classes = list(dataset.get("classes", []))
            classes.sort(key=lambda x: x["id"])
            return classes

    def add_class(self, dataset_id: str, name: str, color: str, class_id: Optional[int] = None) -> Dict[str, Any]:
        if not name or not str(name).strip():
            raise ValueError("class name is required")
        if not color:
            raise ValueError("class color is required")

        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            classes = dataset["classes"]

            existing_ids = {c["id"] for c in classes}
            if class_id is None:
                cid = 0
                while cid in existing_ids:
                    cid += 1
            else:
                cid = int(class_id)
                if cid in existing_ids:
                    raise ValueError("class id already exists")
            if any(c["name"] == name for c in classes):
                raise ValueError("class name already exists")

            item = {"id": cid, "name": name.strip(), "color": color}
            classes.append(item)
            classes.sort(key=lambda x: x["id"])
            dataset["updated_at"] = _utc_now()
            self._save_registry(data)
            return item

    def update_class(
        self,
        dataset_id: str,
        class_id: int,
        name: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            cls = None
            for c in dataset["classes"]:
                if c["id"] == int(class_id):
                    cls = c
                    break
            if not cls:
                raise KeyError("class not found")

            if name is not None:
                if not str(name).strip():
                    raise ValueError("class name cannot be empty")
                if any(c["name"] == name and c["id"] != cls["id"] for c in dataset["classes"]):
                    raise ValueError("class name already exists")
                cls["name"] = name.strip()
            if color is not None:
                cls["color"] = color
            dataset["updated_at"] = _utc_now()
            self._save_registry(data)
            return cls

    def _iter_label_class_ids(self, dataset_id: str, dataset: Dict[str, Any]):
        for version_id in dataset.get("annotation_versions", {}).keys():
            labels_dir = self._version_labels_dir(dataset_id, version_id)
            if not os.path.exists(labels_dir):
                continue
            for name in os.listdir(labels_dir):
                if not name.endswith(".txt"):
                    continue
                label_file = os.path.join(labels_dir, name)
                try:
                    with open(label_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            first = line.split()[0]
                            yield int(first)
                except Exception:
                    continue

    def delete_class(self, dataset_id: str, class_id: int) -> None:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            class_id = int(class_id)
            if class_id in set(self._iter_label_class_ids(dataset_id, dataset)):
                raise RuntimeError("class is used in annotations")

            original_count = len(dataset["classes"])
            dataset["classes"] = [c for c in dataset["classes"] if c["id"] != class_id]
            if len(dataset["classes"]) == original_count:
                raise KeyError("class not found")
            dataset["updated_at"] = _utc_now()
            self._save_registry(data)

    def list_annotation_versions(self, dataset_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            versions = list(dataset.get("annotation_versions", {}).values())
            versions.sort(key=lambda x: x["created_at"], reverse=True)
            return versions

    def create_annotation_version(
        self, dataset_id: str, name: str, source_version_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not name or not str(name).strip():
            raise ValueError("version name is required")
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            versions = dataset["annotation_versions"]
            if any(v["name"] == name for v in versions.values()):
                raise ValueError("annotation version name already exists")

            version_id = str(uuid.uuid4())
            now = _utc_now()
            version = {
                "id": version_id,
                "name": name.strip(),
                "source_version_id": source_version_id,
                "created_at": now,
                "updated_at": now,
            }
            versions[version_id] = version

            target_labels_dir = self._version_labels_dir(dataset_id, version_id)
            os.makedirs(target_labels_dir, exist_ok=True)
            if source_version_id:
                if source_version_id not in versions:
                    raise KeyError("source annotation version not found")
                source_dir = self._version_labels_dir(dataset_id, source_version_id)
                if os.path.exists(source_dir):
                    for name in os.listdir(source_dir):
                        if not name.endswith(".txt"):
                            continue
                        shutil.copy2(os.path.join(source_dir, name), os.path.join(target_labels_dir, name))

            dataset["updated_at"] = _utc_now()
            self._save_registry(data)
            return version

    def update_annotation_version(self, dataset_id: str, version_id: str, name: str) -> Dict[str, Any]:
        if not name or not str(name).strip():
            raise ValueError("version name is required")
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            version = self._require_version(dataset, version_id)
            if any(v["name"] == name and v["id"] != version_id for v in dataset["annotation_versions"].values()):
                raise ValueError("annotation version name already exists")
            version["name"] = name.strip()
            version["updated_at"] = _utc_now()
            dataset["updated_at"] = _utc_now()
            self._save_registry(data)
            return version

    def delete_annotation_version(self, dataset_id: str, version_id: str) -> None:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            self._require_version(dataset, version_id)
            del dataset["annotation_versions"][version_id]
            dataset["updated_at"] = _utc_now()
            self._save_registry(data)
            shutil.rmtree(os.path.join(self._dataset_versions_dir(dataset_id), version_id), ignore_errors=True)

    def get_annotations(self, dataset_id: str, version_id: str, image_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            self._require_version(dataset, version_id)
            if image_id not in dataset.get("images", {}):
                raise KeyError("image not found")
            label_file = os.path.join(self._version_labels_dir(dataset_id, version_id), f"{image_id}.txt")
            if not os.path.exists(label_file):
                return []

            result = []
            with open(label_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) != 5:
                        continue
                    result.append({
                        "class_id": int(parts[0]),
                        "x": float(parts[1]),
                        "y": float(parts[2]),
                        "w": float(parts[3]),
                        "h": float(parts[4]),
                    })
            return result

    @staticmethod
    def _read_annotations_from_file(label_file: str) -> List[Dict[str, Any]]:
        if not os.path.exists(label_file):
            return []
        result = []
        with open(label_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) != 5:
                    continue
                result.append({
                    "class_id": int(parts[0]),
                    "x": float(parts[1]),
                    "y": float(parts[2]),
                    "w": float(parts[3]),
                    "h": float(parts[4]),
                })
        return result

    @staticmethod
    def _annotations_to_lines(annotations: List[Dict[str, Any]], class_ids: set) -> List[str]:
        lines = []
        for i, item in enumerate(annotations):
            try:
                cid = int(item["class_id"])
                x = float(item["x"])
                y = float(item["y"])
                w = float(item["w"])
                h = float(item["h"])
            except Exception as exc:
                raise ValueError(f"invalid annotation at index {i}: {exc}")
            if cid not in class_ids:
                raise ValueError(f"class_id {cid} does not exist")
            for value, key in ((x, "x"), (y, "y"), (w, "w"), (h, "h")):
                if value < 0.0 or value > 1.0:
                    raise ValueError(f"{key} must be between 0 and 1")
            if w <= 0.0 or h <= 0.0:
                raise ValueError("w and h must be > 0")
            lines.append(f"{cid} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
        return lines

    def get_annotations_map(
        self, dataset_id: str, version_id: str, image_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            self._require_version(dataset, version_id)

            images = dataset.get("images", {})
            for image_id in image_ids:
                if image_id not in images:
                    raise KeyError("image not found")

            labels_dir = self._version_labels_dir(dataset_id, version_id)
            result = {}
            for image_id in image_ids:
                label_file = os.path.join(labels_dir, f"{image_id}.txt")
                result[image_id] = self._read_annotations_from_file(label_file)
            return result

    def save_annotations(
        self, dataset_id: str, version_id: str, image_id: str, annotations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            self._require_version(dataset, version_id)
            if image_id not in dataset.get("images", {}):
                raise KeyError("image not found")

            class_ids = {c["id"] for c in dataset.get("classes", [])}
            lines = self._annotations_to_lines(annotations, class_ids)

            labels_dir = self._version_labels_dir(dataset_id, version_id)
            os.makedirs(labels_dir, exist_ok=True)
            label_file = os.path.join(labels_dir, f"{image_id}.txt")
            if lines:
                with open(label_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            else:
                try:
                    os.remove(label_file)
                except FileNotFoundError:
                    pass

            dataset["annotation_versions"][version_id]["updated_at"] = _utc_now()
            dataset["updated_at"] = _utc_now()
            self._save_registry(data)
            return {"saved": len(lines)}

    def save_annotations_bulk(
        self,
        dataset_id: str,
        version_id: str,
        annotations_by_image: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            self._require_version(dataset, version_id)

            images = dataset.get("images", {})
            class_ids = {c["id"] for c in dataset.get("classes", [])}

            lines_by_image = {}
            for image_id, annotations in annotations_by_image.items():
                if image_id not in images:
                    raise KeyError("image not found")
                lines_by_image[image_id] = self._annotations_to_lines(annotations, class_ids)

            labels_dir = self._version_labels_dir(dataset_id, version_id)
            os.makedirs(labels_dir, exist_ok=True)

            saved_boxes = 0
            for image_id, lines in lines_by_image.items():
                label_file = os.path.join(labels_dir, f"{image_id}.txt")
                if lines:
                    with open(label_file, "w", encoding="utf-8") as f:
                        f.write("\n".join(lines) + "\n")
                else:
                    try:
                        os.remove(label_file)
                    except FileNotFoundError:
                        pass
                saved_boxes += len(lines)

            dataset["annotation_versions"][version_id]["updated_at"] = _utc_now()
            dataset["updated_at"] = _utc_now()
            self._save_registry(data)
            return {"saved_images": len(lines_by_image), "saved_boxes": saved_boxes}

    def annotation_stats(self, dataset_id: str, version_id: str) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            self._require_version(dataset, version_id)
            labels_dir = self._version_labels_dir(dataset_id, version_id)
            class_counts = {}
            bbox_count = 0
            labeled_images = 0
            if os.path.exists(labels_dir):
                for name in os.listdir(labels_dir):
                    if not name.endswith(".txt"):
                        continue
                    path = os.path.join(labels_dir, name)
                    has_boxes = False
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            parts = line.split()
                            if not parts:
                                continue
                            cid = int(parts[0])
                            class_counts[cid] = class_counts.get(cid, 0) + 1
                            bbox_count += 1
                            has_boxes = True
                    if has_boxes:
                        labeled_images += 1
            return {
                "total_images": len(dataset.get("images", {})),
                "labeled_images": labeled_images,
                "bbox_count": bbox_count,
                "class_counts": class_counts,
            }

    def get_training_material(self, dataset_id: str, version_id: str) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            dataset = self._require_dataset(data, dataset_id)
            self._require_version(dataset, version_id)
            stats = self.annotation_stats(dataset_id, version_id)
            classes = sorted(dataset.get("classes", []), key=lambda x: x["id"])
            images = list(dataset.get("images", {}).values())
            labels_dir = self._version_labels_dir(dataset_id, version_id)
            images_dir = self._dataset_images_dir(dataset_id)
            return {
                "dataset": dataset,
                "classes": classes,
                "images": images,
                "labels_dir": labels_dir,
                "images_dir": images_dir,
                "stats": stats,
            }

    def split_images(
        self,
        dataset_id: str,
        version_id: str,
        train_ratio: float,
        val_ratio: float,
        test_ratio: float,
        seed: int,
    ) -> Dict[str, List[str]]:
        material = self.get_training_material(dataset_id, version_id)
        image_paths = []
        for image in material["images"]:
            abs_path = os.path.join(material["images_dir"], image["filename"])
            image_paths.append(abs_path)

        rng = random.Random(seed)
        rng.shuffle(image_paths)
        total = len(image_paths)
        n_train = int(total * train_ratio)
        n_val = int(total * val_ratio)
        if n_train + n_val > total:
            n_val = max(0, total - n_train)
        train = image_paths[:n_train]
        val = image_paths[n_train : n_train + n_val]
        test = image_paths[n_train + n_val :]
        if total > 0 and not train:
            train = [image_paths[0]]
            val = image_paths[1:1]
            test = image_paths[1:]
        return {"train": train, "val": val, "test": test}

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._load_registry()
            jobs = list(data.get("jobs", {}).values())
            jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return jobs

    def get_job(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            job = data.get("jobs", {}).get(job_id)
            if not job:
                raise KeyError("job not found")
            return job

    def get_active_job_id(self) -> Optional[str]:
        with self._lock:
            data = self._load_registry()
            return data.get("active_job_id")

    def set_active_job(self, job_id: Optional[str]) -> None:
        with self._lock:
            data = self._load_registry()
            data["active_job_id"] = job_id
            self._save_registry(data)

    def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            job_id = job_data["id"]
            data["jobs"][job_id] = job_data
            data["active_job_id"] = job_id
            self._save_registry(data)
            return job_data

    def update_job(self, job_id: str, updates: Dict[str, Any], clear_active_if_terminal: bool = True) -> Dict[str, Any]:
        with self._lock:
            data = self._load_registry()
            job = data.get("jobs", {}).get(job_id)
            if not job:
                raise KeyError("job not found")
            job.update(updates)
            terminal = {"completed", "failed", "stopped", "interrupted"}
            if clear_active_if_terminal and data.get("active_job_id") == job_id and job.get("status") in terminal:
                data["active_job_id"] = None
            self._save_registry(data)
            return job
