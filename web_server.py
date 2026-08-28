"""MONGDEE AI Booth OS — Web entrypoint.

Runs the exact same AI Vision / Product Assistant / Readiness Check /
Health Monitoring / Dashboard / Trainer feature set as app.py, but served
over HTTP so any browser — on this machine or another device on the same
network (a tablet at the booth counter, for example) — can use it without
installing PySide6.

Usage:
    python web_server.py --booth-name "MONGDEE Demo Booth" --event-id "1-Day-at-IMPACT"
    python web_server.py --host 0.0.0.0 --port 8000   # reachable from other devices on the LAN
"""

from __future__ import annotations

import argparse
import uuid
import webbrowser
from pathlib import Path

import uvicorn

from core import database as db
from core.products import ProductCatalog
from core.recognizer import ProductRecognizer
from core.vision import discover_cameras
from web.booth_manager import BoothManager, load_active_booth_id
from web.server import create_app

ROOT = Path(__file__).resolve().parent


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--booth-id", default=None,
                         help="Omit to reuse the identity last saved via the /settings page, "
                              "or a fresh random ID if none was ever saved.")
    parser.add_argument("--booth-name", default=None)
    parser.add_argument("--event-id", default=None)
    parser.add_argument("--cameras", default=None,
                         help="Comma-separated device paths, e.g. /dev/video0,/dev/video2. "
                              "Omit to auto-discover.")
    parser.add_argument("--model", default=str(ROOT / "yolo11n.pt"))
    parser.add_argument("--db", default=str(db.DEFAULT_DB_PATH))
    parser.add_argument("--products", default=str(ROOT / "products.json"))
    parser.add_argument("--host", default="127.0.0.1",
                         help="0.0.0.0 to allow other devices on the LAN to connect")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-open", action="store_true", help="don't auto-open a browser tab")
    return parser.parse_args()


def resolve_device():
    try:
        import torch

        if torch.cuda.is_available():
            return 0
    except Exception:
        pass
    return "cpu"


def main():
    args = parse_args()
    db_path = Path(args.db)
    db.init_db(db_path)

    # Booth ID / Event ID are real registry rows (core.database's `booths`/
    # `events` tables), not free text — resolve which registry Booth this
    # process should report as. An explicit --booth-id always wins (and
    # auto-registers itself + its event if new, so README's "simulate a
    # second booth" CLI pattern keeps working); otherwise reuse whichever
    # booth was last activated via /settings, so a plain restart doesn't
    # revert to a random identity. A brand-new database bootstraps one booth
    # (+ event) from the CLI defaults so zero-config startup is unchanged.
    if args.booth_id:
        if args.event_id:
            db.ensure_event(db_path, args.event_id)
        if not db.get_booth(db_path, args.booth_id):
            db.create_booth(db_path, args.booth_id, args.booth_name or args.booth_id, args.event_id)
        active_booth_id = args.booth_id
    elif db.count_booths(db_path) == 0:
        boot_event_id = args.event_id or "1-Day-at-IMPACT"
        db.ensure_event(db_path, boot_event_id)
        active_booth_id = f"BOOTH-{uuid.uuid4().hex[:6].upper()}"
        db.create_booth(db_path, active_booth_id, args.booth_name or "MONGDEE Demo Booth", boot_event_id)
    else:
        active_booth_id = load_active_booth_id()
        if not active_booth_id or not db.get_booth(db_path, active_booth_id):
            active_booth_id = db.list_booths(db_path)[0]["id"]

    booth_row = db.get_booth(db_path, active_booth_id)
    booth_id = booth_row["id"]
    booth_name = booth_row["name"]
    event_id = booth_row["event_id"] or ""

    if args.cameras:
        devices = [d.strip() for d in args.cameras.split(",") if d.strip()]
    else:
        print("[WEB] ไม่ได้ระบุกล้อง กำลังค้นหากล้องอัตโนมัติ...")
        devices = discover_cameras()
        print(f"[WEB] พบกล้อง: {devices}")

    if not devices:
        print("[WEB] ไม่พบเว็บแคมที่ใช้งานได้ — เปิดหน้าเว็บต่อได้ตามปกติ "
              "เชื่อมต่อกล้องแล้วรันคำสั่งนี้ใหม่เพื่อให้บูธเห็นกล้อง")

    camera_devices = [(f"CAM-{i+1}", dev) for i, dev in enumerate(devices)]

    print("[WEB] กำลังโหลดโมเดล AI Vision (YOLO11)...")
    from ultralytics import YOLO

    model = YOLO(args.model)
    model_device = resolve_device()
    print(f"[WEB] ใช้งานอุปกรณ์ประมวลผล: {model_device}")

    catalog = ProductCatalog(Path(args.products))

    print("[WEB] กำลังโหลดโมเดล AI จดจำสินค้า (Product Recognizer)...")
    recognizer = ProductRecognizer(device=model_device)

    booth = BoothManager(
        booth_id=booth_id,
        booth_name=booth_name,
        event_id=event_id,
        camera_devices=camera_devices,
        model=model,
        model_device=model_device,
        catalog=catalog,
        recognizer=recognizer,
        db_path=db_path,
    )
    booth.activate_booth(booth_id)  # persist active_booth_id (covers a freshly bootstrapped/new booth)
    app = create_app(booth)

    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}/"
    print(f"[WEB] เปิดใช้งานได้ที่: {url}")
    if args.host == "0.0.0.0":
        print("[WEB] เครื่องอื่นในวง LAN เดียวกันเข้าถึงได้ที่ http://<IP ของเครื่องนี้>:%d/" % args.port)
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
