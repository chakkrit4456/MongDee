"""Headless orchestration shared by the browser booth view — owns the camera
workers, the recognition state, and the in-memory state the API/streams read.

This is the web equivalent of ui/main_window.py, but with no GUI: instead of
Qt Signals updating widgets, core.vision.CameraWorker's plain callbacks
update shared dicts (each behind a lock) that FastAPI request handlers read
directly, since there's no GUI thread to marshal onto here.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path

import cv2

from core import database as db
from core import training
from core.aggregator import DetectionAggregator
from core.readiness import readiness_to_json, run_readiness_check
from core.vision import CameraWorker

HEARTBEAT_INTERVAL_SEC = 30
STREAM_FPS = 12
MAX_ALERTS = 50
JPEG_QUALITY = 80


class BoothManager:
    def __init__(self, booth_id, booth_name, event_id, camera_devices, model,
                 model_device, catalog, recognizer, db_path):
        self.booth_id = booth_id
        self.booth_name = booth_name
        self.event_id = event_id
        self.model = model
        self.model_device = model_device
        self.catalog = catalog
        self.recognizer = recognizer
        self.db_path = db_path

        self.aggregator = DetectionAggregator()
        self.camera_ids = [cid for cid, _ in camera_devices]
        self.camera_devices = dict(camera_devices)

        self._lock = threading.Lock()
        self.camera_status: dict[str, dict] = {
            cid: {"status": "unknown", "message": ""} for cid in self.camera_ids
        }
        self._latest_jpeg: dict[str, bytes] = {}
        self.current_product: dict | None = None
        self.product_seq = 0
        self.recent_alerts: list[dict] = []
        self.import_progress: dict[str, dict] = {}

        self.workers: dict[str, CameraWorker] = {}
        for camera_id, device in camera_devices:
            worker = CameraWorker(
                camera_id=camera_id,
                device=device,
                model=self.model,
                allowed_classes=self.catalog.product_keys(),
                recognizer=self.recognizer,
                device_target=self.model_device,
                on_frame=self._on_frame,
                on_detections=self._on_detections,
                on_status=self._on_status,
            )
            self.workers[camera_id] = worker

        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)

    # ------------------------------------------------------------- lifecycle
    def start(self):
        for worker in self.workers.values():
            worker.start()
        self._heartbeat_thread.start()

    def stop(self):
        self._heartbeat_stop.set()
        for worker in self.workers.values():
            worker.stop()
        db.log_heartbeat(self.db_path, self.booth_id, self.event_id, "stopped", 0)

    def _heartbeat_loop(self):
        while not self._heartbeat_stop.wait(HEARTBEAT_INTERVAL_SEC):
            with self._lock:
                active = sum(1 for s in self.camera_status.values() if s["status"] == "online")
            overall = "ok" if active > 0 else "degraded"
            db.log_heartbeat(self.db_path, self.booth_id, self.event_id, overall, active)

    # ----------------------------------------------------------- callbacks
    def _on_frame(self, camera_id, frame):
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok:
            with self._lock:
                self._latest_jpeg[camera_id] = buf.tobytes()

    def _on_detections(self, camera_id, detections):
        event = self.aggregator.update(camera_id, detections)
        if event:
            self._handle_product_recognized(event)

    def _on_status(self, camera_id, status, message):
        with self._lock:
            previous = self.camera_status[camera_id]["status"]
            self.camera_status[camera_id] = {"status": status, "message": message}
        if status == previous:
            return

        severity = "ok" if status == "online" else ("error" if status == "offline" else "warning")
        db.log_health_event(self.db_path, self.booth_id, self.event_id, camera_id,
                             "camera", severity, message)
        if status != "online":
            self._push_alert(f"⚠️ {camera_id}: {message}")
        elif previous not in ("unknown",):
            self._push_alert(f"✅ {camera_id}: กลับมาออนไลน์แล้ว")
        else:
            self._push_alert(f"🔌 {camera_id}: เชื่อมต่อสำเร็จ")

    def _push_alert(self, text: str):
        with self._lock:
            self.recent_alerts.insert(0, {"ts": time.time(), "text": text})
            self.recent_alerts = self.recent_alerts[:MAX_ALERTS]

    def _handle_product_recognized(self, event: dict):
        class_name = event["class_name"]
        product = self.catalog.get(class_name)
        if not product:
            return
        source = ", ".join(event["cameras"])
        with self._lock:
            self.current_product = {
                "key": class_name,
                "name": product["name"],
                "tagline": product.get("tagline", ""),
                "description": product.get("description", ""),
                "confidence": event["confidence"],
                "cameras": source,
                "speak_text": f"{product['name']}. {product['description']}",
            }
            self.product_seq += 1
        db.log_interaction(self.db_path, self.booth_id, self.event_id, source, class_name,
                            product["name"], event["confidence"])
        self._push_alert(f"🟢 พบสินค้า: {product['name']} ({source})")

    # ------------------------------------------------------------- readers
    def get_latest_jpeg(self, camera_id: str) -> bytes | None:
        with self._lock:
            return self._latest_jpeg.get(camera_id)

    def get_state(self) -> dict:
        with self._lock:
            return {
                "booth_id": self.booth_id,
                "booth_name": self.booth_name,
                "event_id": self.event_id,
                "cameras": {cid: dict(v) for cid, v in self.camera_status.items()},
                "current_product": dict(self.current_product) if self.current_product else None,
                "product_seq": self.product_seq,
                "recent_alerts": list(self.recent_alerts[:20]),
            }

    def ask(self, question: str) -> dict:
        with self._lock:
            product = dict(self.current_product) if self.current_product else None
        if not product:
            return {"answer": "กรุณานำสินค้าไปวางในกรอบกล้องก่อน แล้วจึงถามคำถามค่ะ"}
        answer = self.catalog.answer_question(product["key"], question)
        db.log_interaction(self.db_path, self.booth_id, self.event_id, "assistant",
                            product["key"], product["name"], None, question, answer)
        return {"answer": answer}

    def run_readiness(self) -> dict:
        with self._lock:
            statuses = {cid: v["status"] for cid, v in self.camera_status.items()}
        report = run_readiness_check(
            camera_statuses=statuses,
            model_loaded=self.model is not None,
            tts_available=True,  # spoken via the browser's Web Speech API, not the server
            db_path=self.db_path,
        )
        db.log_readiness_check(self.db_path, self.booth_id, self.event_id,
                                "ready" if report["overall_ok"] else "not_ready",
                                readiness_to_json(report))
        return report

    # ------------------------------------------------------------ training
    def start_image_import(self, product_key: str, filenames_and_bytes: list[tuple[str, bytes]]):
        if self.import_progress.get(product_key, {}).get("status") == "running":
            raise RuntimeError("มีงานนำเข้าอยู่แล้วสำหรับสินค้านี้ กรุณารอให้เสร็จก่อน")
        self.import_progress[product_key] = {"done": 0, "total": len(filenames_and_bytes), "status": "running"}

        def job():
            tmp_dir = tempfile.mkdtemp(prefix="mongdee_upload_")
            try:
                paths = []
                for name, content in filenames_and_bytes:
                    path = Path(tmp_dir) / name
                    path.write_bytes(content)
                    paths.append(str(path))

                def progress_cb(done, total):
                    self.import_progress[product_key] = {"done": done, "total": total, "status": "running"}

                added = training.import_images(paths, product_key, self.recognizer,
                                                self.model, self.model_device, progress_cb)
                self.import_progress[product_key] = {"done": added, "total": added, "status": "done"}
            except Exception as exc:
                self.import_progress[product_key] = {"done": 0, "total": 0, "status": "error", "message": str(exc)}
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        threading.Thread(target=job, daemon=True).start()

    def start_video_import(self, product_key: str, filename: str, content: bytes):
        if self.import_progress.get(product_key, {}).get("status") == "running":
            raise RuntimeError("มีงานนำเข้าอยู่แล้วสำหรับสินค้านี้ กรุณารอให้เสร็จก่อน")
        self.import_progress[product_key] = {"done": 0, "total": 0, "status": "running"}

        def job():
            tmp_dir = tempfile.mkdtemp(prefix="mongdee_upload_")
            try:
                path = Path(tmp_dir) / filename
                path.write_bytes(content)

                def progress_cb(done, total):
                    self.import_progress[product_key] = {"done": done, "total": total, "status": "running"}

                added = training.import_video(str(path), product_key, self.recognizer,
                                               self.model, self.model_device, progress_cb)
                self.import_progress[product_key] = {"done": added, "total": added, "status": "done"}
            except Exception as exc:
                self.import_progress[product_key] = {"done": 0, "total": 0, "status": "error", "message": str(exc)}
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        threading.Thread(target=job, daemon=True).start()
