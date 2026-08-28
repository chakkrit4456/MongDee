"""Qt adapter for core.vision.CameraWorker.

core/vision.py is intentionally framework-agnostic (plain threading +
callbacks) so the web server can use it directly. The PySide6 desktop UI
still wants Qt Signals (so cross-thread delivery onto the GUI thread is
handled automatically by Qt's queued connections) — this class wraps a
plain CameraWorker and re-exposes its three callbacks as signals, keeping
the exact same interface main_window.py/trainer_window.py already use.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.vision import CameraWorker as _PlainCameraWorker


class QtCameraWorker(QObject):
    frame_ready = Signal(str, object)          # camera_id, BGR ndarray (with boxes drawn)
    detections_ready = Signal(str, list)       # camera_id, [{"class_name","conf","bbox"}]
    status_changed = Signal(str, str, str)     # camera_id, status ("online"/"offline"), message

    def __init__(self, camera_id: str, device, model, allowed_classes: list[str],
                 recognizer=None, conf_threshold: float = 0.45, device_target="cpu",
                 show_unknown: bool = True, parent=None):
        super().__init__(parent)
        self._worker = _PlainCameraWorker(
            camera_id=camera_id,
            device=device,
            model=model,
            allowed_classes=allowed_classes,
            recognizer=recognizer,
            conf_threshold=conf_threshold,
            device_target=device_target,
            show_unknown=show_unknown,
            on_frame=self.frame_ready.emit,
            on_detections=self.detections_ready.emit,
            on_status=self.status_changed.emit,
        )

    @property
    def camera_id(self) -> str:
        return self._worker.camera_id

    def start(self):
        self._worker.start()

    def stop(self):
        self._worker.stop()
