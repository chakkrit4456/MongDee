"""Headless orchestration shared by the browser booth view — owns the camera
workers, the recognition state, and the in-memory state the API/streams read.

This is the web equivalent of ui/main_window.py, but with no GUI: instead of
Qt Signals updating widgets, core.vision.CameraWorker's plain callbacks
update shared dicts (each behind a lock) that FastAPI request handlers read
directly, since there's no GUI thread to marshal onto here.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
from pathlib import Path

import cv2

from core import database as db
from core import training
from core.aggregator import DetectionAggregator
from core.interest_tracker import ProductInterestTracker
from core.readiness import readiness_to_json, run_readiness_check
from core.vision import CameraWorker

HEARTBEAT_INTERVAL_SEC = 30
STREAM_FPS = 12
MAX_ALERTS = 50
JPEG_QUALITY = 80
MIN_PRESENCE_DURATION_SEC = 1.0   # denoise single-frame false-positive person detections

BOOTH_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "booth_settings.json"


def load_active_booth_id(path: Path = BOOTH_SETTINGS_PATH) -> str | None:
    """Which registry Booth (core.database's `booths` table) this process
    should report as, saved whenever /settings activates a different one —
    see web_server.py's startup, which reads this before falling back to a
    freshly-bootstrapped booth."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("active_booth_id")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


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
        self.started_at = time.time()

        self.aggregator = DetectionAggregator()
        self.interest_tracker = ProductInterestTracker()
        self.camera_ids = [cid for cid, _ in camera_devices]
        self.camera_devices = dict(camera_devices)

        self._lock = threading.Lock()
        self.camera_status: dict[str, dict] = {
            cid: {"status": "unknown", "message": ""} for cid in self.camera_ids
        }
        self._latest_jpeg: dict[str, bytes] = {}
        self._person_tracks: dict[str, list[dict]] = {cid: [] for cid in self.camera_ids}
        self.current_product: dict | None = None
        self.product_seq = 0
        self.recent_alerts: list[dict] = []
        self.import_progress: dict[str, dict] = {}

        self._next_camera_num = len(self.camera_ids) + 1

        self.workers: dict[str, CameraWorker] = {}
        for camera_id, device in camera_devices:
            worker = self._make_worker(camera_id, device)
            self.workers[camera_id] = worker

        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)

    def _make_worker(self, camera_id: str, device) -> CameraWorker:
        return CameraWorker(
            camera_id=camera_id,
            device=device,
            model=self.model,
            allowed_classes=self.catalog.product_keys(),
            recognizer=self.recognizer,
            device_target=self.model_device,
            on_frame=self._on_frame,
            on_detections=self._on_detections,
            on_status=self._on_status,
            on_person_tracks=self._on_person_tracks,
        )

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
        with self._lock:
            person_tracks = self._person_tracks.get(camera_id, [])

        event = self.aggregator.update(camera_id, detections)
        if event:
            self._handle_product_recognized(event)

        for hold in self.interest_tracker.update(camera_id, detections, person_tracks):
            product = self.catalog.get(hold["class_name"])
            db.log_product_hold_event(
                self.db_path, self.booth_id, self.event_id, camera_id, hold["class_name"],
                product["name"] if product else hold["class_name"], hold["holder_track_id"],
                hold["hold_start_ts"], hold["hold_end_ts"], hold["duration_sec"],
            )

    def _on_person_tracks(self, camera_id, visible_tracks, evicted_tracks):
        with self._lock:
            self._person_tracks[camera_id] = visible_tracks
        for track in evicted_tracks:
            duration = track["last_seen"] - track["first_seen"]
            if duration >= MIN_PRESENCE_DURATION_SEC:
                db.log_presence_session(self.db_path, self.booth_id, self.event_id, camera_id,
                                         track["track_id"], track["first_seen"], track["last_seen"],
                                         duration)

    def _on_status(self, camera_id, status, message):
        with self._lock:
            previous = self.camera_status[camera_id]["status"]
            self.camera_status[camera_id] = {"status": status, "message": message}
            if status != "online":
                self._person_tracks[camera_id] = []
        if status == previous:
            return

        severity = "ok" if status == "online" else ("error" if status == "offline" else "warning")
        db.log_health_event(self.db_path, self.booth_id, self.event_id, camera_id,
                             "camera", severity, message)
        if status != "online":
            self._push_alert("camera_offline", f"{camera_id}: {message}")
        elif previous not in ("unknown",):
            self._push_alert("camera_online", f"{camera_id}: กลับมาออนไลน์แล้ว")
        else:
            self._push_alert("camera_connected", f"{camera_id}: เชื่อมต่อสำเร็จ")

    def _push_alert(self, alert_type: str, text: str):
        with self._lock:
            self.recent_alerts.insert(0, {"ts": time.time(), "type": alert_type, "text": text})
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
                "price": product.get("price", ""),
                "description": product.get("description", ""),
                "faq": product.get("faq", []),
                "confidence": event["confidence"],
                "cameras": source,
                "speak_text": f"{product['name']}. {product['description']}",
            }
            self.product_seq += 1
        db.log_interaction(self.db_path, self.booth_id, self.event_id, source, class_name,
                            product["name"], event["confidence"])
        self._push_alert("product_found", f"พบสินค้า: {product['name']} ({source})")

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
                "people_now": sum(len(v) for v in self._person_tracks.values()),
            }

    def get_live_analytics(self) -> dict:
        with self._lock:
            people_now = sum(len(v) for v in self._person_tracks.values())
        products = self.interest_tracker.live_states()
        for p in products:
            product = self.catalog.get(p["class_name"])
            p["product_name"] = product["name"] if product else p["class_name"]
        return {"people_now": people_now, "products": products}

    # -------------------------------------------------------- booth settings
    def get_settings(self) -> dict:
        with self._lock:
            return {
                "booth_id": self.booth_id,
                "booth_name": self.booth_name,
                "event_id": self.event_id,
                "cameras": [
                    {"camera_id": cid, "device": str(self.camera_devices.get(cid, ""))}
                    for cid in self.camera_ids
                ],
            }

    def activate_booth(self, booth_id: str) -> None:
        """Switch which registry Booth (core.database's `booths` table) this
        running process reports as — the only way identity changes now that
        Booth ID / Event ID are real registry rows, not free text. Persists
        the choice so it survives a restart."""
        booth_row = db.get_booth(self.db_path, booth_id)
        if not booth_row:
            raise ValueError(f"ไม่พบบูธ {booth_id} ในระบบ")
        with self._lock:
            self.booth_id = booth_row["id"]
            self.booth_name = booth_row["name"]
            self.event_id = booth_row["event_id"] or ""
        BOOTH_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BOOTH_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({"active_booth_id": booth_id}, f, ensure_ascii=False, indent=2)

    def remove_booth(self, booth_id: str) -> None:
        """Permanently delete a registry Booth and all its logged data.
        Refuses to delete the currently active one — it's still being
        written to live, so a one-time data wipe could never actually
        stick; the caller must activate a different booth first."""
        with self._lock:
            active = self.booth_id
        if booth_id == active:
            raise ValueError("ไม่สามารถลบบูธที่กำลังใช้งานอยู่ได้ กรุณาเปลี่ยนไปใช้บูธอื่นก่อน")
        db.delete_booth(self.db_path, booth_id)

    def add_camera(self, device) -> str:
        with self._lock:
            camera_id = f"CAM-{self._next_camera_num}"
            self._next_camera_num += 1
            self.camera_ids.append(camera_id)
            self.camera_devices[camera_id] = device
            self.camera_status[camera_id] = {"status": "unknown", "message": ""}
            self._person_tracks[camera_id] = []

        worker = self._make_worker(camera_id, device)
        with self._lock:
            self.workers[camera_id] = worker
        worker.start()
        return camera_id

    def remove_camera(self, camera_id: str) -> None:
        with self._lock:
            worker = self.workers.pop(camera_id, None)
            if camera_id in self.camera_ids:
                self.camera_ids.remove(camera_id)
            self.camera_devices.pop(camera_id, None)
            self.camera_status.pop(camera_id, None)
            self._latest_jpeg.pop(camera_id, None)
            self._person_tracks.pop(camera_id, None)
        if worker is not None:
            worker.stop()  # blocks on thread join — never call while holding self._lock

    def reset_data(self) -> None:
        """Wipe every logged row (interactions, health, hold events, presence
        sessions, ...) for this booth_id — irreversible. The API layer is
        responsible for getting user confirmation before calling this."""
        db.delete_scope_data(self.db_path, booth_id=self.booth_id)

    def run_readiness(self) -> dict:
        with self._lock:
            statuses = {cid: v["status"] for cid, v in self.camera_status.items()}
            workers_snapshot = dict(self.workers)
        resolutions = {cid: w.get_resolution() for cid, w in workers_snapshot.items()}
        report = run_readiness_check(
            camera_statuses=statuses,
            model_loaded=self.model is not None,
            tts_available=True,  # spoken via the browser's Web Speech API, not the server
            db_path=self.db_path,
            camera_resolutions=resolutions,
            camera_devices=self.camera_devices,
            model_device=self.model_device,
            started_at=self.started_at,
        )
        db.log_readiness_check(self.db_path, self.booth_id, self.event_id,
                                "ready" if report["overall_ok"] else "not_ready",
                                readiness_to_json(report))
        return report

    # ------------------------------------------------------------ training
    def start_image_import(self, product_key: str, filenames_and_bytes: list[tuple[str, bytes]]):
        with self._lock:
            if self.import_progress.get(product_key, {}).get("status") == "running":
                raise RuntimeError("มีงานนำเข้าอยู่แล้วสำหรับสินค้านี้ กรุณารอให้เสร็จก่อน")
            self.import_progress[product_key] = {
                "done": 0, "total": len(filenames_and_bytes), "status": "running"
            }

        def job():
            tmp_dir = tempfile.mkdtemp(prefix="mongdee_upload_")
            try:
                paths = []
                for index, (name, content) in enumerate(filenames_and_bytes):
                    # Upload names are untrusted and may contain ../ or an
                    # absolute path. Keep every temporary file inside tmp_dir.
                    safe_name = Path(name).name or "image.bin"
                    path = Path(tmp_dir) / f"{index:04d}-{safe_name}"
                    path.write_bytes(content)
                    paths.append(str(path))

                def progress_cb(done, total):
                    self._set_import_progress(
                        product_key, {"done": done, "total": total, "status": "running"}
                    )

                added = training.import_images(paths, product_key, self.recognizer,
                                                self.model, self.model_device, progress_cb)
                self._set_import_progress(
                    product_key, {"done": added, "total": added, "status": "done"}
                )
            except Exception as exc:
                self._set_import_progress(product_key, {
                    "done": 0, "total": 0, "status": "error", "message": str(exc)
                })
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        threading.Thread(target=job, daemon=True).start()

    def start_video_import(self, product_key: str, filename: str, content: bytes):
        with self._lock:
            if self.import_progress.get(product_key, {}).get("status") == "running":
                raise RuntimeError("มีงานนำเข้าอยู่แล้วสำหรับสินค้านี้ กรุณารอให้เสร็จก่อน")
            self.import_progress[product_key] = {
                "done": 0, "total": 0, "status": "running"
            }

        def job():
            tmp_dir = tempfile.mkdtemp(prefix="mongdee_upload_")
            try:
                safe_name = Path(filename).name or "video.bin"
                path = Path(tmp_dir) / safe_name
                path.write_bytes(content)

                def progress_cb(done, total):
                    self._set_import_progress(
                        product_key, {"done": done, "total": total, "status": "running"}
                    )

                added = training.import_video(str(path), product_key, self.recognizer,
                                               self.model, self.model_device, progress_cb)
                self._set_import_progress(
                    product_key, {"done": added, "total": added, "status": "done"}
                )
            except Exception as exc:
                self._set_import_progress(product_key, {
                    "done": 0, "total": 0, "status": "error", "message": str(exc)
                })
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        threading.Thread(target=job, daemon=True).start()

    def _set_import_progress(self, product_key: str, state: dict) -> None:
        with self._lock:
            self.import_progress[product_key] = state

    def get_import_progress(self, product_key: str) -> dict:
        with self._lock:
            return dict(self.import_progress.get(
                product_key, {"done": 0, "total": 0, "status": "idle"}
            ))
