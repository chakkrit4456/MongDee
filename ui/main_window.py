"""Main booth window: live multi-camera AI Vision + AI Product Assistant."""

from __future__ import annotations

import json
import time

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import database as db
from core.aggregator import DetectionAggregator
from core.readiness import readiness_to_json, run_readiness_check
from ui.qt_camera_bridge import QtCameraWorker as CameraWorker

HEARTBEAT_INTERVAL_MS = 30_000

STATUS_COLORS = {
    "online": "#2ecc71",
    "offline": "#e74c3c",
    "error": "#e67e22",
    "unknown": "#7f8c8d",
}


def frame_to_pixmap(frame_bgr) -> QPixmap:
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = frame_rgb.shape
    qimg = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class CameraPanel(QFrame):
    def __init__(self, camera_id: str, device: str):
        super().__init__()
        self.camera_id = camera_id
        self.device = device

        self.video = QLabel("กำลังเชื่อมต่อ...")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(320, 240)
        self.video.setStyleSheet(
            "QLabel { background: #111318; color: #888; border-radius: 10px; font-size: 14px; }"
        )

        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {STATUS_COLORS['unknown']}; font-size: 16px;")

        title = QLabel(f"{camera_id}  ({device})")
        title.setFont(QFont("Sans", 10, QFont.Bold))
        title.setStyleSheet("color: white;")

        header = QHBoxLayout()
        header.addWidget(self.dot)
        header.addWidget(title)
        header.addStretch(1)

        self.status_label = QLabel("กำลังเชื่อมต่อ...")
        self.status_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.video, 1)
        layout.addWidget(self.status_label)

        self.setStyleSheet(
            "QFrame { background: #181a20; border: 1px solid #30333d; border-radius: 12px; }"
        )

    def set_frame(self, frame_bgr):
        pixmap = frame_to_pixmap(frame_bgr)
        self.video.setPixmap(
            pixmap.scaled(self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def set_status(self, status: str, message: str):
        color = STATUS_COLORS.get(status, STATUS_COLORS["unknown"])
        self.dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        self.status_label.setText(message)
        if status != "online":
            self.video.setText(f"❌ {message}")


class ReadinessDialog(QDialog):
    def __init__(self, report: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ผลการตรวจสอบความพร้อมของบูธ (Booth Readiness Check)")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        headline = "✅ บูธพร้อมใช้งาน (READY)" if report["overall_ok"] else "❌ บูธยังไม่พร้อม (NOT READY)"
        headline_label = QLabel(headline)
        headline_label.setFont(QFont("Sans", 14, QFont.Bold))
        headline_label.setStyleSheet(
            "color: %s;" % ("#2ecc71" if report["overall_ok"] else "#e74c3c")
        )
        layout.addWidget(headline_label)

        listw = QListWidget()
        for c in report["components"]:
            icon = "✅" if c["ok"] else ("❌" if c["critical"] else "⚠️")
            item = QListWidgetItem(f"{icon}  {c['component']} — {c['detail']}")
            listw.addItem(item)
        layout.addWidget(listw)

        close_btn = QPushButton("ปิด")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setStyleSheet("QDialog { background: #101218; color: white; }"
                            "QListWidget { background: #181a20; color: white; border: none; }")


class MainWindow(QWidget):
    def __init__(self, booth_id, booth_name, event_id, camera_devices, model,
                 model_device, catalog, assistant, db_path, recognizer=None,
                 dashboard_launcher=None, trainer_launcher=None):
        super().__init__()
        self.booth_id = booth_id
        self.booth_name = booth_name
        self.event_id = event_id
        self.model = model
        self.catalog = catalog
        self.assistant = assistant
        self.db_path = db_path
        self.recognizer = recognizer
        self.dashboard_launcher = dashboard_launcher
        self.trainer_launcher = trainer_launcher

        self.aggregator = DetectionAggregator()
        self.camera_panels: dict[str, CameraPanel] = {}
        self.camera_status: dict[str, str] = {}
        self.workers: list[CameraWorker] = []
        self.current_product_key: str | None = None

        self.setWindowTitle(f"MONGDEE AI Booth OS — {booth_name}")
        self.resize(1440, 860)
        self._build_ui(camera_devices)
        self._create_workers(camera_devices, model_device)

        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self._send_heartbeat)
        self.heartbeat_timer.start(HEARTBEAT_INTERVAL_MS)

    # ------------------------------------------------------------------ UI
    def _build_ui(self, camera_devices):
        root = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        title = QLabel(f"MONGDEE AI Booth OS  •  Booth: {self.booth_name} ({self.booth_id})  •  Event: {self.event_id}")
        title.setFont(QFont("Sans", 13, QFont.Bold))
        title.setStyleSheet("color: white;")
        top_bar.addWidget(title)
        top_bar.addStretch(1)

        self.readiness_pill = QLabel("ยังไม่ตรวจสอบ")
        self.readiness_pill.setStyleSheet(
            "background: #444; color: white; padding: 4px 12px; border-radius: 10px;"
        )
        top_bar.addWidget(self.readiness_pill)

        readiness_btn = QPushButton("🔍 ตรวจสอบความพร้อมบูธ")
        readiness_btn.clicked.connect(self._on_run_readiness)
        top_bar.addWidget(readiness_btn)

        trainer_btn = QPushButton("🎓 เทรน AI จดจำสินค้า")
        trainer_btn.clicked.connect(self._on_open_trainer)
        top_bar.addWidget(trainer_btn)

        dashboard_btn = QPushButton("📊 เปิด Dashboard")
        dashboard_btn.clicked.connect(self._on_open_dashboard)
        top_bar.addWidget(dashboard_btn)

        root.addLayout(top_bar)

        legend = QLabel('<span style="color:#2ecc71;">■</span> สินค้า (Product)&nbsp;&nbsp;&nbsp;'
                         '<span style="color:#ff3c3c;">■</span> คน (Person)&nbsp;&nbsp;&nbsp;'
                         '<span style="color:#969696;">■</span> พบวัตถุแต่ยังไม่รู้จัก (ควรเทรน)')
        legend.setStyleSheet("padding: 2px 0 6px 2px;")
        root.addWidget(legend)

        body = QHBoxLayout()

        cam_grid_widget = QWidget()
        self.cam_grid = QGridLayout(cam_grid_widget)
        cols = 2 if len(camera_devices) > 1 else 1
        for i, (camera_id, device) in enumerate(camera_devices):
            panel = CameraPanel(camera_id, device)
            self.camera_panels[camera_id] = panel
            self.camera_status[camera_id] = "unknown"
            self.cam_grid.addWidget(panel, i // cols, i % cols)
        body.addWidget(cam_grid_widget, 2)

        body.addWidget(self._build_assistant_panel(), 1)

        root.addLayout(body, 1)

        alerts_label = QLabel("🔔 การแจ้งเตือนล่าสุด (Booth Health Monitoring)")
        alerts_label.setStyleSheet("color: white; font-weight: bold; padding-top: 6px;")
        root.addWidget(alerts_label)

        self.alerts_list = QListWidget()
        self.alerts_list.setMaximumHeight(120)
        root.addWidget(self.alerts_list)

        self.setStyleSheet("""
            QWidget { background: #101218; color: white; }
            QPushButton { background: #20232c; border: 1px solid #383c48; border-radius: 8px;
                          padding: 8px 14px; color: white; }
            QPushButton:hover { background: #2b2f3a; }
            QLineEdit, QTextEdit { background: #181a20; border: 1px solid #30333d;
                                    border-radius: 6px; color: white; padding: 6px; }
            QListWidget { background: #181a20; border: 1px solid #30333d; border-radius: 6px; color: white; }
        """)

    def _build_assistant_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet("QFrame { background: #181a20; border: 1px solid #30333d; border-radius: 12px; }")
        layout = QVBoxLayout(panel)

        header = QLabel("🤖 AI Product Assistant")
        header.setFont(QFont("Sans", 13, QFont.Bold))
        layout.addWidget(header)

        self.product_name_label = QLabel("ยังไม่พบสินค้า — วางสินค้าในกรอบกล้องเพื่อเริ่มต้น")
        self.product_name_label.setWordWrap(True)
        self.product_name_label.setFont(QFont("Sans", 15, QFont.Bold))
        layout.addWidget(self.product_name_label)

        self.product_tagline_label = QLabel("")
        self.product_tagline_label.setStyleSheet("color: #7fd3ff;")
        self.product_tagline_label.setWordWrap(True)
        layout.addWidget(self.product_tagline_label)

        self.product_desc_label = QLabel("")
        self.product_desc_label.setWordWrap(True)
        self.product_desc_label.setStyleSheet("color: #cccccc;")
        layout.addWidget(self.product_desc_label)

        self.product_source_label = QLabel("")
        self.product_source_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(self.product_source_label)

        layout.addSpacing(8)
        ask_label = QLabel("💬 พิมพ์คำถามเกี่ยวกับสินค้านี้")
        layout.addWidget(ask_label)

        ask_row = QHBoxLayout()
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("เช่น ราคาเท่าไหร่ / มีสีอะไรบ้าง")
        self.question_input.returnPressed.connect(self._on_ask)
        ask_row.addWidget(self.question_input)
        ask_btn = QPushButton("ถาม")
        ask_btn.clicked.connect(self._on_ask)
        ask_row.addWidget(ask_btn)
        layout.addLayout(ask_row)

        self.answer_label = QLabel("")
        self.answer_label.setWordWrap(True)
        self.answer_label.setStyleSheet("color: #ffe08a; padding-top: 4px;")
        layout.addWidget(self.answer_label)

        layout.addSpacing(8)
        history_label = QLabel("🕘 ประวัติการโต้ตอบ")
        layout.addWidget(history_label)
        self.history_list = QListWidget()
        layout.addWidget(self.history_list, 1)

        return panel

    # -------------------------------------------------------------- workers
    def _create_workers(self, camera_devices, model_device):
        for camera_id, device in camera_devices:
            worker = CameraWorker(
                camera_id=camera_id,
                device=device,
                model=self.model,
                allowed_classes=self.catalog.product_keys(),
                recognizer=self.recognizer,
                device_target=model_device,
            )
            worker.frame_ready.connect(self._on_frame_ready)
            worker.detections_ready.connect(self._on_detections_ready)
            worker.status_changed.connect(self._on_status_changed)
            self.workers.append(worker)
            worker.start()

    # --------------------------------------------------------------- slots
    def _on_frame_ready(self, camera_id, frame):
        panel = self.camera_panels.get(camera_id)
        if panel:
            panel.set_frame(frame)

    def _on_detections_ready(self, camera_id, detections):
        event = self.aggregator.update(camera_id, detections)
        if event:
            self._handle_product_recognized(event)

    def _on_status_changed(self, camera_id, status, message):
        previous = self.camera_status.get(camera_id)
        self.camera_status[camera_id] = status
        panel = self.camera_panels.get(camera_id)
        if panel:
            panel.set_status(status, message)

        if status == previous:
            return

        severity = "ok" if status == "online" else ("error" if status == "offline" else "warning")
        db.log_health_event(self.db_path, self.booth_id, self.event_id, camera_id,
                             "camera", severity, message)
        if status != "online":
            self._push_alert(f"⚠️ {camera_id}: {message}")
        elif previous not in (None, "unknown"):
            self._push_alert(f"✅ {camera_id}: กลับมาออนไลน์แล้ว")
        else:
            self._push_alert(f"🔌 {camera_id}: เชื่อมต่อสำเร็จ")

    def _push_alert(self, text: str):
        item = QListWidgetItem(f"[{time.strftime('%H:%M:%S')}] {text}")
        self.alerts_list.insertItem(0, item)
        while self.alerts_list.count() > 50:
            self.alerts_list.takeItem(self.alerts_list.count() - 1)

    def _handle_product_recognized(self, event: dict):
        class_name = event["class_name"]
        self.current_product_key = class_name
        product = self.assistant.describe(class_name, speak=True)
        if not product:
            return

        self.product_name_label.setText(product["name"])
        self.product_tagline_label.setText(product["tagline"])
        self.product_desc_label.setText(product["description"])
        source = ", ".join(event["cameras"])
        reason = "กล้องหลายตัวยืนยันพร้อมกัน" if event["reason"] == "multi_camera_agreement" else "ตรวจพบต่อเนื่อง"
        self.product_source_label.setText(
            f"ตรวจพบโดยกล้อง: {source}  •  {reason}  •  ความมั่นใจ {event['confidence']:.0%}"
        )
        self.answer_label.setText("")

        db.log_interaction(
            self.db_path, self.booth_id, self.event_id, source, class_name,
            product["name"], event["confidence"],
        )
        self._add_history(f"🟢 พบสินค้า: {product['name']} ({source})")

    def _on_ask(self):
        question = self.question_input.text().strip()
        if not question:
            return
        if not self.current_product_key:
            self.answer_label.setText("กรุณานำสินค้าไปวางในกรอบกล้องก่อน แล้วจึงถามคำถามค่ะ")
            return

        answer = self.assistant.answer(self.current_product_key, question, speak=True)
        self.answer_label.setText(answer)
        product = self.catalog.get(self.current_product_key)
        db.log_interaction(
            self.db_path, self.booth_id, self.event_id, "assistant", self.current_product_key,
            product["name"] if product else self.current_product_key, None, question, answer,
        )
        self._add_history(f"❓ {question}  →  {answer}")
        self.question_input.clear()

    def _add_history(self, text: str):
        self.history_list.insertItem(0, QListWidgetItem(f"[{time.strftime('%H:%M:%S')}] {text}"))
        while self.history_list.count() > 100:
            self.history_list.takeItem(self.history_list.count() - 1)

    def _on_run_readiness(self):
        report = run_readiness_check(
            camera_statuses=self.camera_status,
            model_loaded=self.model is not None,
            tts_available=self.assistant.tts_available,
            db_path=self.db_path,
        )
        db.log_readiness_check(
            self.db_path, self.booth_id, self.event_id,
            "ready" if report["overall_ok"] else "not_ready",
            readiness_to_json(report),
        )
        if report["overall_ok"]:
            self.readiness_pill.setText("✅ READY")
            self.readiness_pill.setStyleSheet(
                "background: #1e6b3a; color: white; padding: 4px 12px; border-radius: 10px;"
            )
        else:
            self.readiness_pill.setText("❌ NOT READY")
            self.readiness_pill.setStyleSheet(
                "background: #7a1f1f; color: white; padding: 4px 12px; border-radius: 10px;"
            )
        ReadinessDialog(report, self).exec()

    def _on_open_dashboard(self):
        if self.dashboard_launcher:
            self.dashboard_launcher()

    def _on_open_trainer(self):
        if self.trainer_launcher:
            self.trainer_launcher()

    def _send_heartbeat(self):
        active = sum(1 for s in self.camera_status.values() if s == "online")
        overall = "ok" if active > 0 else "degraded"
        db.log_heartbeat(self.db_path, self.booth_id, self.event_id, overall, active)

    # -------------------------------------------------------------- close
    def closeEvent(self, event):
        for worker in self.workers:
            worker.stop()
        db.log_heartbeat(self.db_path, self.booth_id, self.event_id, "stopped", 0)
        event.accept()
