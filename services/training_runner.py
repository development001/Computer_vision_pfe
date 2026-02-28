import os
import re
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

import yaml


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrainingRunner:
    PRESET_MODELS = {"yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"}

    def __init__(self, base_dir: str, models_dir: str, store):
        self.base_dir = base_dir
        self.models_dir = models_dir
        self.store = store
        self._lock = threading.RLock()
        self._runtime: Dict[str, Dict[str, object]] = {}

    def initialize(self) -> None:
        active = self.store.get_active_job_id()
        if not active:
            return
        try:
            job = self.store.get_job(active)
        except KeyError:
            self.store.set_active_job(None)
            return
        if job.get("status") in {"starting", "running"}:
            self.store.update_job(
                active,
                {
                    "status": "interrupted",
                    "ended_at": _utc_now(),
                    "message": "training process was interrupted during restart",
                },
            )

    def _resolve_model_source(self, model_source: str) -> str:
        model_source = (model_source or "").strip()
        if not model_source:
            raise ValueError("model_source is required")
        if model_source in self.PRESET_MODELS:
            return model_source

        model_name = os.path.basename(model_source)
        if not model_name.endswith(".pt"):
            raise ValueError("custom model must be a .pt file")
        abs_path = os.path.join(self.models_dir, model_name)
        if not os.path.exists(abs_path):
            raise ValueError(f"model not found: {model_name}")
        return abs_path

    def _validate_class_ids(self, classes):
        if not classes:
            raise ValueError("dataset has no classes")
        ids = sorted(c["id"] for c in classes)
        expected = list(range(len(classes)))
        if ids != expected:
            raise ValueError("class IDs must be contiguous and start at 0 for YOLO training")
        return [c["name"] for c in sorted(classes, key=lambda x: x["id"])]

    def _validate_ratios(self, train_ratio: float, val_ratio: float, test_ratio: float) -> None:
        for ratio in (train_ratio, val_ratio, test_ratio):
            if ratio < 0.0 or ratio > 1.0:
                raise ValueError("split ratios must be between 0 and 1")
        total = train_ratio + val_ratio + test_ratio
        if abs(total - 1.0) > 1e-6:
            raise ValueError("split ratios must sum to 1.0")

    def start_job(self, payload: Dict[str, object]) -> Dict[str, object]:
        dataset_id = str(payload.get("dataset_id") or "")
        version_id = str(payload.get("annotation_version_id") or "")
        model_source = str(payload.get("model_source") or "")
        epochs = int(payload.get("epochs", 50))
        batch_size = int(payload.get("batch_size", 16))
        imgsz = int(payload.get("imgsz", 640))
        split_train = float(payload.get("split_train", 0.8))
        split_val = float(payload.get("split_val", 0.1))
        split_test = float(payload.get("split_test", 0.1))
        seed = int(payload.get("seed", 42))

        self._validate_ratios(split_train, split_val, split_test)
        model_path = self._resolve_model_source(model_source)
        material = self.store.get_training_material(dataset_id, version_id)
        stats = material["stats"]
        if stats["labeled_images"] <= 0:
            raise ValueError("selected annotation version has zero labeled images")

        names = self._validate_class_ids(material["classes"])
        splits = self.store.split_images(dataset_id, version_id, split_train, split_val, split_test, seed)

        with self._lock:
            active = self.store.get_active_job_id()
            if active:
                active_job = self.store.get_job(active)
                if active_job.get("status") in {"starting", "running"}:
                    raise RuntimeError("another training job is already running")

            job_id = str(uuid.uuid4())
            now = _utc_now()
            job_dir = os.path.join(self.base_dir, "jobs", job_id)
            splits_dir = os.path.join(job_dir, "splits")
            runs_dir = os.path.join(job_dir, "runs")
            os.makedirs(splits_dir, exist_ok=True)
            os.makedirs(runs_dir, exist_ok=True)

            train_txt = os.path.join(splits_dir, "train.txt")
            val_txt = os.path.join(splits_dir, "val.txt")
            test_txt = os.path.join(splits_dir, "test.txt")
            self._write_list(train_txt, splits["train"])
            self._write_list(val_txt, splits["val"])
            self._write_list(test_txt, splits["test"])

            dataset_yaml_path = os.path.join(job_dir, "dataset.yaml")
            with open(dataset_yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    {
                        "train": train_txt,
                        "val": val_txt,
                        "test": test_txt,
                        "nc": len(names),
                        "names": names,
                    },
                    f,
                    sort_keys=False,
                )

            logs_path = os.path.join(job_dir, "logs.txt")
            state_path = os.path.join(job_dir, "state.json")
            cmd = [
                "yolo",
                "detect",
                "train",
                f"model={model_path}",
                f"data={dataset_yaml_path}",
                f"epochs={epochs}",
                f"batch={batch_size}",
                f"imgsz={imgsz}",
                f"project={runs_dir}",
                "name=run",
            ]

            job = {
                "id": job_id,
                "dataset_id": dataset_id,
                "annotation_version_id": version_id,
                "model_source": model_source,
                "resolved_model": model_path,
                "epochs": epochs,
                "batch_size": batch_size,
                "imgsz": imgsz,
                "split_train": split_train,
                "split_val": split_val,
                "split_test": split_test,
                "seed": seed,
                "status": "starting",
                "progress_pct": 0.0,
                "epoch_current": 0,
                "epoch_total": epochs,
                "metrics": {},
                "created_at": now,
                "started_at": now,
                "ended_at": None,
                "job_dir": job_dir,
                "logs_path": logs_path,
                "state_path": state_path,
                "command": cmd,
                "message": "",
            }
            self.store.create_job(job)
            self._runtime[job_id] = {"stop_event": threading.Event(), "process": None}
            thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
            self._runtime[job_id]["thread"] = thread
            thread.start()
            return job

    def _write_list(self, path: str, rows) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(f"{row}\n")

    def _parse_progress(self, line: str, epoch_total: int) -> Optional[int]:
        # Ultralytics commonly logs "1/100" per epoch; parse that pattern.
        match = re.search(r"\b(\d+)\s*/\s*(\d+)\b", line)
        if not match:
            return None
        cur = int(match.group(1))
        tot = int(match.group(2))
        if tot <= 0:
            return None
        if epoch_total and tot != epoch_total:
            return None
        if cur < 0:
            return None
        return cur

    def _run_job(self, job_id: str) -> None:
        try:
            job = self.store.get_job(job_id)
        except KeyError:
            return

        runtime = self._runtime.get(job_id)
        if not runtime:
            return
        stop_event = runtime["stop_event"]
        process = None
        try:
            os.makedirs(os.path.dirname(job["logs_path"]), exist_ok=True)
            with open(job["logs_path"], "a", encoding="utf-8") as logf:
                self.store.update_job(job_id, {"status": "running", "message": ""}, clear_active_if_terminal=False)
                process = subprocess.Popen(
                    job["command"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                with self._lock:
                    if job_id in self._runtime:
                        self._runtime[job_id]["process"] = process

                epoch_total = int(job.get("epoch_total") or 0)
                epoch_current = 0
                for line in process.stdout:
                    if line is None:
                        continue
                    logf.write(line)
                    logf.flush()
                    parsed = self._parse_progress(line, epoch_total)
                    if parsed is not None and parsed >= epoch_current:
                        epoch_current = parsed
                        progress = 0.0 if epoch_total <= 0 else min(100.0, (epoch_current / epoch_total) * 100.0)
                        self.store.update_job(
                            job_id,
                            {"epoch_current": epoch_current, "progress_pct": progress},
                            clear_active_if_terminal=False,
                        )
                    if stop_event.is_set():
                        break

                return_code = process.wait(timeout=10)
                if stop_event.is_set():
                    status = "stopped"
                    message = "training stopped by user"
                elif return_code == 0:
                    status = "completed"
                    message = "training completed"
                else:
                    status = "failed"
                    message = f"training exited with code {return_code}"
                self.store.update_job(
                    job_id,
                    {
                        "status": status,
                        "message": message,
                        "ended_at": _utc_now(),
                        "progress_pct": 100.0 if status == "completed" else self.store.get_job(job_id).get("progress_pct", 0.0),
                    },
                )
        except Exception as exc:
            self.store.update_job(
                job_id,
                {"status": "failed", "message": str(exc), "ended_at": _utc_now()},
            )
        finally:
            if process and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass
            with self._lock:
                self._runtime.pop(job_id, None)

    def list_jobs(self):
        return self.store.list_jobs()

    def get_job(self, job_id: str):
        return self.store.get_job(job_id)

    def stop_job(self, job_id: str) -> Dict[str, object]:
        with self._lock:
            runtime = self._runtime.get(job_id)
            if runtime:
                runtime["stop_event"].set()
                process = runtime.get("process")
                if process and process.poll() is None:
                    try:
                        process.terminate()
                    except Exception:
                        pass
            else:
                job = self.store.get_job(job_id)
                if job.get("status") not in {"starting", "running"}:
                    return job
        return self.store.update_job(
            job_id,
            {"status": "stopped", "message": "stop requested", "ended_at": _utc_now()},
        )

    def get_logs(self, job_id: str, offset: int = 0, limit: int = 20000) -> Dict[str, object]:
        job = self.store.get_job(job_id)
        logs_path = job.get("logs_path")
        if not logs_path or not os.path.exists(logs_path):
            return {"offset": 0, "next_offset": 0, "chunk": ""}
        with open(logs_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(max(0, offset))
            chunk = f.read(limit)
            next_offset = f.tell()
        return {"offset": offset, "next_offset": next_offset, "chunk": chunk}

