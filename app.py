"""MONGDEE AI Booth OS — entrypoint.

Launches the booth window: N webcams running AI Vision concurrently, the AI
Product Assistant, Booth Readiness Check, Booth Health Monitoring, and a
link into the AI Dashboard & Analytics window. See README.md for the full
feature-to-spec mapping.

Usage:
    python app.py --booth-id BOOTH-01 --booth-name "MONGDEE Demo Booth" \
        --event-id "1-Day-at-IMPACT" --cameras /dev/video0,/dev/video2
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from core import database as db
from core.assistant import AIAssistant
from core.products import ProductCatalog
from core.recognizer import ProductRecognizer
from core.vision import discover_cameras
from ui.dashboard_window import DashboardWindow
from ui.main_window import MainWindow
from ui.trainer_window import TrainerWindow

ROOT = Path(__file__).resolve().parent


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--booth-id", default=f"BOOTH-{uuid.uuid4().hex[:6].upper()}")
    parser.add_argument("--booth-name", default="MONGDEE Demo Booth")
    parser.add_argument("--event-id", default="1-Day-at-IMPACT")
    parser.add_argument("--cameras", default=None,
                         help="Comma-separated device paths, e.g. /dev/video0,/dev/video2. "
                              "Omit to auto-discover.")
    parser.add_argument("--model", default=str(ROOT / "yolo11n.pt"))
    parser.add_argument("--conf", type=float, default=0.45)
    parser.add_argument("--db", default=str(db.DEFAULT_DB_PATH))
    parser.add_argument("--products", default=str(ROOT / "products.json"))
    return parser.parse_args()


def resolve_device():
    try:
        import torch

        if torch.cuda.is_available():
            return 0
    except Exception:
        pass
    return "cpu"


def load_model(model_path: str):
    from ultralytics import YOLO

    return YOLO(model_path)


def main():
    args = parse_args()
    db_path = Path(args.db)
    db.init_db(db_path)

    if args.cameras:
        devices = [d.strip() for d in args.cameras.split(",") if d.strip()]
    else:
        print("[BOOTH] ไม่ได้ระบุกล้อง กำลังค้นหากล้องอัตโนมัติ...")
        devices = discover_cameras()
        print(f"[BOOTH] พบกล้อง: {devices}")

    app = QApplication(sys.argv)

    if not devices:
        QMessageBox.critical(None, "ไม่พบกล้อง", "ไม่พบเว็บแคมที่ใช้งานได้ กรุณาเชื่อมต่อกล้องแล้วลองใหม่")
        sys.exit(1)

    camera_devices = [(f"CAM-{i+1}", dev) for i, dev in enumerate(devices)]

    print("[BOOTH] กำลังโหลดโมเดล AI Vision (YOLO11)...")
    model = load_model(args.model)
    model_device = resolve_device()
    print(f"[BOOTH] ใช้งานอุปกรณ์ประมวลผล: {model_device}")

    catalog = ProductCatalog(Path(args.products))
    assistant = AIAssistant(catalog)
    if not assistant.tts_available:
        print(f"[BOOTH] เสียงพูด (TTS) ไม่พร้อมใช้งาน: {assistant.tts_error} "
              "— ระบบจะยังทำงานได้แบบข้อความ")

    print("[BOOTH] กำลังโหลดโมเดล AI จดจำสินค้า (Product Recognizer)...")
    recognizer = ProductRecognizer(device=model_device)

    dashboard_ref = {}
    trainer_ref = {}

    def open_dashboard():
        if "window" not in dashboard_ref or not dashboard_ref["window"].isVisible():
            dashboard_ref["window"] = DashboardWindow(db_path, default_event_id=args.event_id)
        dashboard_ref["window"].show()
        dashboard_ref["window"].raise_()
        dashboard_ref["window"].activateWindow()

    def open_trainer():
        if "window" not in trainer_ref or not trainer_ref["window"].isVisible():
            trainer_ref["window"] = TrainerWindow(catalog, recognizer, model, model_device)
        trainer_ref["window"].show()
        trainer_ref["window"].raise_()
        trainer_ref["window"].activateWindow()

    window = MainWindow(
        booth_id=args.booth_id,
        booth_name=args.booth_name,
        event_id=args.event_id,
        camera_devices=camera_devices,
        model=model,
        model_device=model_device,
        catalog=catalog,
        assistant=assistant,
        db_path=db_path,
        recognizer=recognizer,
        dashboard_launcher=open_dashboard,
        trainer_launcher=open_trainer,
    )
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
