"""Booth Readiness Check — a pre-event diagnostic of every subsystem.

Mirrors spec item 3 (Booth Readiness Check): before a booth opens, staff
run this once to confirm cameras, the AI model, storage, TTS and the mic
are all working, instead of checking each device by hand.
"""

from __future__ import annotations

import json
import sqlite3
import time


def check_database(db_path) -> tuple[bool, str]:
    try:
        with sqlite3.connect(db_path, timeout=3) as conn:
            conn.execute("SELECT 1")
        return True, "เชื่อมต่อฐานข้อมูลสำเร็จ"
    except Exception as exc:
        return False, f"เชื่อมต่อฐานข้อมูลไม่สำเร็จ: {exc}"


def check_microphone() -> tuple[bool, str]:
    try:
        import sounddevice as sd

        devices = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        if devices:
            return True, f"พบไมโครโฟน {len(devices)} อุปกรณ์"
        return False, "ไม่พบไมโครโฟนที่ใช้งานได้"
    except Exception as exc:
        return False, f"ตรวจสอบไมโครโฟนไม่สำเร็จ: {exc}"


def run_readiness_check(camera_statuses: dict[str, str], model_loaded: bool,
                         tts_available: bool, db_path) -> dict:
    """camera_statuses: {camera_id: "online"/"offline"/"error"}."""
    components = []

    for camera_id, status in camera_statuses.items():
        ok = status == "online"
        components.append({
            "component": f"กล้อง {camera_id}",
            "critical": True,
            "ok": ok,
            "detail": "พร้อมใช้งาน" if ok else f"สถานะ: {status}",
        })

    components.append({
        "component": "โมเดล AI Vision (YOLO11)",
        "critical": True,
        "ok": model_loaded,
        "detail": "โหลดโมเดลสำเร็จ" if model_loaded else "โหลดโมเดลไม่สำเร็จ",
    })

    db_ok, db_msg = check_database(db_path)
    components.append({"component": "ฐานข้อมูล", "critical": True, "ok": db_ok, "detail": db_msg})

    components.append({
        "component": "ระบบเสียงพูด (Text-to-Speech)",
        "critical": False,
        "ok": tts_available,
        "detail": "พร้อมใช้งาน" if tts_available else "ไม่พร้อมใช้งาน (ระบบจะยังทำงานได้แบบข้อความ)",
    })

    mic_ok, mic_msg = check_microphone()
    components.append({"component": "ไมโครโฟน", "critical": False, "ok": mic_ok, "detail": mic_msg})

    critical_failed = [c for c in components if c["critical"] and not c["ok"]]
    overall_ok = len(critical_failed) == 0

    return {
        "ts": time.time(),
        "overall_ok": overall_ok,
        "components": components,
    }


def readiness_to_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False)
