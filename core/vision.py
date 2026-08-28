"""AI Vision: per-camera capture + detection threads.

Framework-agnostic on purpose: this module only depends on cv2/numpy/threading,
not on any GUI toolkit, so the exact same detection pipeline runs inside the
PySide6 desktop app (via ui/qt_camera_bridge.py, which adapts the callbacks
below into Qt Signals) and inside the browser-facing web server
(web/server.py, which reads the callbacks directly since it has no GUI
thread to marshal onto). Each camera runs in its own thread so N webcams run
concurrently. Two independent detectors feed the same overlay/aggregator:

  1. YOLO11 (COCO classes) — cheap, exact, but only knows 80 generic object
     types. Used for "person" (always) and for demo products whose catalog
     key happens to be a COCO class name (bottle, cup, ...).
  2. ForegroundProposer + ProductRecognizer (core/localizer.py,
     core/recognizer.py) — class-agnostic: finds "something is being shown"
     via background subtraction, then identifies *which* trained product it
     is via image-embedding matching. This is what makes real, arbitrary
     products (never in COCO) recognizable once someone has uploaded a few
     training photos through the AI Trainer.

Both YOLO inference and embedding inference are serialized behind locks
(neither ultralytics' nor torch's forward pass is guaranteed safe under
concurrent calls from multiple threads) but each camera keeps capturing and
running its own background model independently, so a slow/stuck camera
never blocks the others.
"""

from __future__ import annotations

import threading
import time

import cv2

from core.localizer import ForegroundProposer, crop_box

FAIL_THRESHOLD = 20          # consecutive failed reads before a camera is flagged offline
REOPEN_INTERVAL_SEC = 3.0    # how often to retry opening a dead camera
DETECT_EVERY_N_FRAMES = 2    # run detection every Nth frame to keep multi-camera FPS reasonable
MIN_CROP_SIDE_PX = 24        # ignore foreground blobs too small to embed meaningfully

PERSON_CLASS_NAME = "person"
PERSON_COLOR = (50, 60, 235)      # BGR red — คน
PRODUCT_COLOR = (0, 200, 0)       # BGR green — สินค้า (รู้จักแล้ว)
UNKNOWN_COLOR = (150, 150, 150)   # BGR gray — พบวัตถุแต่ยังไม่รู้จัก (ยังไม่ได้เทรน)
BOX_THICKNESS = 2
LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX
LABEL_SCALE = 0.55

_inference_lock = threading.Lock()


def _draw_box(frame, bbox, label, color):
    x1, y1, x2, y2 = [int(v) for v in bbox]
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, BOX_THICKNESS)
    (tw, th), baseline = cv2.getTextSize(label, LABEL_FONT, LABEL_SCALE, 2)
    label_top = max(0, y1 - th - baseline - 6)
    cv2.rectangle(frame, (x1, label_top), (x1 + tw + 6, y1), color, -1)
    cv2.putText(frame, label, (x1 + 3, y1 - 5), LABEL_FONT, LABEL_SCALE, (255, 255, 255), 2)


def _ascii_label(text: str) -> str:
    """cv2.putText's built-in Hershey font can't render Thai glyphs (they come
    out as "??"), so any non-ASCII product key falls back to a generic word
    for the on-frame label; the real Thai name still shows in the AI Product
    Assistant panel, which Qt renders correctly."""
    return text.upper() if text.isascii() else "PRODUCT"


def discover_cameras(max_index: int = 8, max_found: int = 4) -> list[str]:
    """Probe /dev/video* nodes and return the ones that actually deliver frames."""
    found = []
    for i in range(max_index):
        device = f"/dev/video{i}"
        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        try:
            if cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    found.append(device)
        finally:
            cap.release()
        if len(found) >= max_found:
            break
    return found


class CameraWorker(threading.Thread):
    """Runs one camera's capture+detection loop on a background thread.

    Callers get results via three optional callback attributes instead of
    Qt signals, so this class has no GUI dependency:
      - on_frame(camera_id, frame_bgr)          — every frame, with boxes drawn
      - on_detections(camera_id, detections)    — only on frames inference ran
      - on_status(camera_id, status, message)   — only on status transitions
    Each callback fires synchronously from this thread — callers touching a
    GUI must marshal onto their own main thread themselves (see
    ui/qt_camera_bridge.py for the Qt adapter); the web server just reads
    shared state directly since it's already thread-based.
    """

    def __init__(self, camera_id: str, device, model, allowed_classes: list[str],
                 recognizer=None, conf_threshold: float = 0.45, device_target="cpu",
                 show_unknown: bool = True, on_frame=None, on_detections=None, on_status=None):
        super().__init__(daemon=True)
        self.camera_id = camera_id
        self.device = device
        self.model = model
        self.recognizer = recognizer
        self.conf_threshold = conf_threshold
        self.device_target = device_target
        self.show_unknown = show_unknown
        self.on_frame = on_frame or (lambda *a: None)
        self.on_detections = on_detections or (lambda *a: None)
        self.on_status = on_status or (lambda *a: None)

        # Catalog keys that double as a YOLO/COCO class name get the cheap,
        # exact detection path; everything else (custom-trained products) is
        # only findable via the embedding recognizer.
        catalog_keys = set(allowed_classes)
        coco_names = set(model.names.values())
        self._legacy_coco_classes = catalog_keys & coco_names
        detect_classes = self._legacy_coco_classes | {PERSON_CLASS_NAME}
        self._class_indices = [
            idx for idx, name in model.names.items() if name in detect_classes
        ]

        self._proposer = ForegroundProposer()
        self._running = False
        self._cap = None
        self._last_status = None
        self._last_boxes: list[tuple[list[float], str, tuple[int, int, int]]] = []

    def _open(self) -> bool:
        cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            return False
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap
        return True

    def _emit_status(self, status: str, message: str = ""):
        if status != self._last_status:
            self._last_status = status
            self.on_status(self.camera_id, status, message)

    def _run_yolo(self, frame):
        """Returns (person_boxes, legacy_product_detections, claimed_boxes)."""
        person_boxes = []
        legacy_detections = []
        claimed_boxes = []
        if not self._class_indices:
            return person_boxes, legacy_detections, claimed_boxes
        with _inference_lock:
            results = self.model.predict(
                source=frame,
                imgsz=640,
                conf=self.conf_threshold,
                classes=self._class_indices,
                device=self.device_target,
                verbose=False,
            )
        if not results or results[0].boxes is None:
            return person_boxes, legacy_detections, claimed_boxes
        for box in results[0].boxes:
            class_id = int(box.cls.item())
            class_name = self.model.names[class_id]
            conf = float(box.conf.item())
            bbox = [float(x) for x in box.xyxy[0].tolist()]
            claimed_boxes.append(bbox)
            if class_name == PERSON_CLASS_NAME:
                person_boxes.append(bbox)
                self._last_boxes.append((bbox, f"PERSON {conf:.0%}", PERSON_COLOR))
            else:
                self._last_boxes.append((bbox, f"{class_name.upper()} {conf:.0%}", PRODUCT_COLOR))
                legacy_detections.append({"class_name": class_name, "conf": conf, "bbox": bbox})
        return person_boxes, legacy_detections, claimed_boxes

    def _run_custom_recognition(self, frame, claimed_boxes):
        """Foreground blobs not already claimed by YOLO get identified against
        the trained embedding gallery (arbitrary, non-COCO products)."""
        detections = []
        if self.recognizer is None:
            return detections
        proposals = self._proposer.propose(frame, exclude_boxes=claimed_boxes, max_regions=2)
        for bbox in proposals:
            crop = crop_box(frame, bbox)
            if crop.shape[0] < MIN_CROP_SIDE_PX or crop.shape[1] < MIN_CROP_SIDE_PX:
                continue
            try:
                product_key, score = self.recognizer.identify(crop)
            except Exception:
                continue
            if product_key:
                label = f"{_ascii_label(product_key)} {score:.0%}"
                self._last_boxes.append((bbox, label, PRODUCT_COLOR))
                detections.append({"class_name": product_key, "conf": score, "bbox": bbox})
            elif self.show_unknown and self.recognizer.has_any_gallery():
                self._last_boxes.append((bbox, f"UNKNOWN {score:.0%}", UNKNOWN_COLOR))
        return detections

    def run(self):
        self._running = True
        if not self._open():
            self._emit_status("offline", f"เปิดกล้อง {self.device} ไม่สำเร็จ")

        fail_count = 0
        last_reopen_attempt = 0.0
        frame_number = 0

        while self._running:
            if self._cap is None or not self._cap.isOpened():
                now = time.time()
                if now - last_reopen_attempt >= REOPEN_INTERVAL_SEC:
                    last_reopen_attempt = now
                    if self._open():
                        fail_count = 0
                        self._emit_status("online", "เชื่อมต่อกล้องสำเร็จ")
                    else:
                        self._emit_status("offline", f"ไม่พบกล้อง {self.device}")
                time.sleep(0.2)
                continue

            ok, frame = self._cap.read()
            if not ok or frame is None:
                fail_count += 1
                if fail_count >= FAIL_THRESHOLD:
                    self._emit_status("offline", "อ่านภาพจากกล้องไม่ได้ต่อเนื่อง")
                    self._cap.release()
                    self._cap = None
                time.sleep(0.03)
                continue

            fail_count = 0
            self._emit_status("online", "ปกติ")
            frame_number += 1

            ran_inference = frame_number % DETECT_EVERY_N_FRAMES == 0
            if ran_inference:
                detections = []
                self._last_boxes = []
                try:
                    person_boxes, legacy_detections, claimed_boxes = self._run_yolo(frame)
                    detections.extend(legacy_detections)
                    detections.extend(self._run_custom_recognition(frame, claimed_boxes))
                except Exception as exc:
                    self._emit_status("error", f"AI ตรวจจับล้มเหลว: {exc}")
            else:
                self._proposer.update(frame)

            # Boxes from the last inference pass stay drawn on every frame in
            # between (inference only runs every DETECT_EVERY_N_FRAMES-th
            # frame) so they don't flicker on/off at the video's frame rate.
            display_frame = frame.copy() if self._last_boxes else frame
            for bbox, label, color in self._last_boxes:
                _draw_box(display_frame, bbox, label, color)

            self.on_frame(self.camera_id, display_frame)
            if ran_inference:
                self.on_detections(self.camera_id, detections)

        if self._cap is not None:
            self._cap.release()

    def stop(self):
        self._running = False
        self.join(timeout=2)
