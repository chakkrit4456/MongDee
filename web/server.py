"""FastAPI app: everything the desktop app does, reachable from any browser
on the same machine or the local network — booth view (live streams + AI
Product Assistant + readiness check + health alerts), Dashboard, and AI
Trainer. See web_server.py for the CLI entrypoint that builds this app.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import database as db
from core.export import build_workbook
from core.recognizer import RECOMMENDED_SAMPLES
from web.booth_manager import STREAM_FPS, BoothManager

WEB_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_ROOT / "templates"))


def create_app(booth: BoothManager) -> FastAPI:
    app = FastAPI(title="MONGDEE AI Booth OS")
    app.mount("/static", StaticFiles(directory=str(WEB_ROOT / "static")), name="static")

    @app.on_event("startup")
    def _start_booth():
        booth.start()

    @app.on_event("shutdown")
    def _stop_booth():
        booth.stop()

    # --------------------------------------------------------------- pages
    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request, "index.html", {
            "booth_id": booth.booth_id, "booth_name": booth.booth_name,
            "event_id": booth.event_id,
        })

    @app.get("/booth")
    def booth_page(request: Request):
        return templates.TemplateResponse(request, "booth.html", {
            "booth_id": booth.booth_id, "booth_name": booth.booth_name,
            "event_id": booth.event_id, "camera_ids": booth.camera_ids,
        })

    @app.get("/product-view")
    def product_view_page(request: Request):
        return templates.TemplateResponse(request, "product_view.html", {
            "booth_id": booth.booth_id, "booth_name": booth.booth_name,
            "event_id": booth.event_id, "camera_ids": booth.camera_ids,
        })

    @app.get("/booth/camera/{camera_id}")
    def booth_camera_page(request: Request, camera_id: str):
        if camera_id not in booth.camera_ids:
            raise HTTPException(404, "ไม่พบกล้องนี้")
        return templates.TemplateResponse(request, "camera_view.html", {
            "booth_id": booth.booth_id, "booth_name": booth.booth_name,
            "event_id": booth.event_id, "camera_id": camera_id,
        })

    @app.get("/dashboard")
    def dashboard_page(request: Request):
        return templates.TemplateResponse(request, "dashboard.html", {
            "booth_id": booth.booth_id, "event_id": booth.event_id,
        })

    @app.get("/trainer")
    def trainer_page(request: Request):
        return templates.TemplateResponse(request, "trainer.html", {
            "camera_ids": booth.camera_ids,
            "recommended_samples": RECOMMENDED_SAMPLES,
        })

    @app.get("/settings")
    def settings_page(request: Request):
        return templates.TemplateResponse(request, "settings.html", {})

    # ------------------------------------------------------------ streaming
    @app.get("/stream/{camera_id}")
    def stream(camera_id: str):
        if camera_id not in booth.camera_ids:
            raise HTTPException(404, "ไม่พบกล้องนี้")

        def generate():
            boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            while True:
                frame = booth.get_latest_jpeg(camera_id)
                if frame:
                    yield boundary + frame + b"\r\n"
                time.sleep(1 / STREAM_FPS)

        return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

    # ---------------------------------------------------------------- booth API
    @app.get("/api/state")
    def api_state():
        return booth.get_state()

    @app.post("/api/readiness")
    def api_readiness():
        return booth.run_readiness()

    # -------------------------------------------------------- booth settings
    @app.get("/api/booth/settings")
    def api_booth_settings():
        return booth.get_settings()

    # -------------------------------------------------------- event/booth registry
    @app.get("/api/registry/events")
    def api_list_events():
        return db.list_events(booth.db_path)

    @app.post("/api/registry/events")
    def api_create_event(payload: dict):
        from core.training import slugify

        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "กรุณาระบุชื่อ Event")
        existing = {e["id"] for e in db.list_events(booth.db_path)}
        event_id = slugify(name, prefix="event")
        while event_id in existing:
            event_id = f"{event_id}-{int(time.time() * 1000) % 10000}"
        db.create_event(booth.db_path, event_id, name)
        return {"id": event_id}

    @app.put("/api/registry/events/{event_id}")
    def api_rename_event(event_id: str, payload: dict):
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "กรุณาระบุชื่อ Event")
        db.rename_event(booth.db_path, event_id, name)
        return {"ok": True}

    @app.delete("/api/registry/events/{event_id}")
    def api_delete_event(event_id: str):
        db.delete_event(booth.db_path, event_id)
        booth.activate_booth(booth.booth_id)  # refresh event_id if the active booth was a member
        return {"ok": True}

    @app.get("/api/registry/booths")
    def api_list_booths():
        return [{**b, "active": b["id"] == booth.booth_id} for b in db.list_booths(booth.db_path)]

    @app.post("/api/registry/booths")
    def api_create_booth(payload: dict):
        from core.training import slugify

        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "กรุณาระบุชื่อบูธ")
        existing = {b["id"] for b in db.list_booths(booth.db_path)}
        booth_id = slugify(name, prefix="booth").upper()
        while booth_id in existing:
            booth_id = f"{booth_id}-{int(time.time() * 1000) % 10000}"
        db.create_booth(booth.db_path, booth_id, name, payload.get("event_id") or None)
        return {"id": booth_id}

    @app.put("/api/registry/booths/{booth_id}")
    def api_update_booth(booth_id: str, payload: dict):
        if not db.get_booth(booth.db_path, booth_id):
            raise HTTPException(404, "ไม่พบบูธนี้")
        kwargs = {}
        if "name" in payload:
            kwargs["name"] = payload.get("name")
        if "event_id" in payload:
            kwargs["event_id"] = payload.get("event_id") or None  # "" or missing = unassign
        db.update_booth(booth.db_path, booth_id, **kwargs)
        if booth_id == booth.booth_id:
            booth.activate_booth(booth_id)  # refresh live name/event_id
        return {"ok": True}

    @app.delete("/api/registry/booths/{booth_id}")
    def api_delete_booth(booth_id: str):
        if not db.get_booth(booth.db_path, booth_id):
            raise HTTPException(404, "ไม่พบบูธนี้")
        try:
            booth.remove_booth(booth_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {"ok": True}

    @app.post("/api/registry/booths/{booth_id}/activate")
    def api_activate_booth(booth_id: str):
        try:
            booth.activate_booth(booth_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        return booth.get_settings()

    @app.post("/api/booth/cameras")
    def api_add_camera(payload: dict):
        device = (payload.get("device") or "").strip()
        if not device:
            raise HTTPException(400, "กรุณาระบุกล้อง เช่น 0 หรือ /dev/video0")
        camera_id = booth.add_camera(device)
        return {"camera_id": camera_id}

    @app.delete("/api/booth/cameras/{camera_id}")
    def api_remove_camera(camera_id: str):
        if camera_id not in booth.camera_ids:
            raise HTTPException(404, "ไม่พบกล้องนี้")
        booth.remove_camera(camera_id)
        return {"ok": True}

    @app.post("/api/booth/reset_data")
    def api_reset_booth_data():
        booth.reset_data()
        return {"ok": True}

    # ------------------------------------------------------------- products API
    @app.get("/api/products")
    def api_products():
        counts = booth.recognizer.sample_counts()
        return [
            {"key": key, **booth.catalog.get(key), "sample_count": counts.get(key, 0)}
            for key in booth.catalog.product_keys()
        ]

    @app.post("/api/products")
    def api_add_product(payload: dict):
        from core.training import slugify

        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "กรุณาระบุชื่อสินค้า")
        key = slugify(name)
        while booth.catalog.get(key):
            key = f"{key}-{int(time.time() * 1000) % 10000}"
        booth.catalog.add_product(key, name, payload.get("tagline", ""), payload.get("description", ""),
                                   payload.get("faq"), payload.get("price", ""))
        return {"key": key}

    @app.put("/api/products/{key}")
    def api_update_product(key: str, payload: dict):
        if not booth.catalog.get(key):
            raise HTTPException(404, "ไม่พบสินค้านี้")
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "กรุณาระบุชื่อสินค้า")
        booth.catalog.add_product(key, name, payload.get("tagline", ""), payload.get("description", ""),
                                   payload.get("faq"), payload.get("price", ""))
        return {"key": key}

    @app.delete("/api/products/{key}")
    def api_delete_product(key: str):
        booth.catalog.remove_product(key)
        booth.recognizer.clear_product(key)
        return {"ok": True}

    @app.post("/api/products/{key}/upload_images")
    async def api_upload_images(key: str, files: list[UploadFile] = File(...)):
        if not booth.catalog.get(key):
            raise HTTPException(404, "ไม่พบสินค้านี้")
        payload = [(f.filename or "image.jpg", await f.read()) for f in files]
        try:
            booth.start_image_import(key, payload)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return {"status": "started"}

    @app.post("/api/products/{key}/upload_video")
    async def api_upload_video(key: str, file: UploadFile = File(...)):
        if not booth.catalog.get(key):
            raise HTTPException(404, "ไม่พบสินค้านี้")
        content = await file.read()
        try:
            booth.start_video_import(key, file.filename or "video.mp4", content)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return {"status": "started"}

    @app.get("/api/products/{key}/import_progress")
    def api_import_progress(key: str):
        return booth.import_progress.get(key, {"done": 0, "total": 0, "status": "idle"})

    @app.post("/api/products/{key}/clear_samples")
    def api_clear_samples(key: str):
        booth.recognizer.clear_product(key)
        return {"ok": True}

    # ------------------------------------------------------------ dashboard API
    @app.get("/api/dashboard/summary")
    def api_dashboard_summary(event_id: str | None = None, booth_id: str | None = None):
        return db.query_summary(booth.db_path, event_id, booth_id)

    @app.get("/api/dashboard/top_products")
    def api_dashboard_top_products(event_id: str | None = None, booth_id: str | None = None):
        return db.query_top_products(booth.db_path, event_id, booth_id)

    @app.get("/api/dashboard/interactions")
    def api_dashboard_interactions(event_id: str | None = None, booth_id: str | None = None):
        return db.query_interactions(booth.db_path, event_id, booth_id)

    @app.get("/api/dashboard/health")
    def api_dashboard_health(event_id: str | None = None, booth_id: str | None = None):
        return db.query_health_events(booth.db_path, event_id, booth_id)

    @app.get("/api/dashboard/live")
    def api_dashboard_live():
        return booth.get_live_analytics()

    @app.get("/api/dashboard/product_movers")
    def api_dashboard_product_movers(event_id: str | None = None, booth_id: str | None = None):
        return db.query_product_movers(booth.db_path, event_id, booth_id)

    @app.get("/api/dashboard/presence_stats")
    def api_dashboard_presence_stats(event_id: str | None = None, booth_id: str | None = None):
        return db.query_presence_stats(booth.db_path, event_id, booth_id)

    @app.get("/api/dashboard/product_hold_history")
    def api_dashboard_product_hold_history(event_id: str | None = None, booth_id: str | None = None):
        return db.query_product_hold_events(booth.db_path, event_id, booth_id)

    @app.get("/api/dashboard/presence_sessions")
    def api_dashboard_presence_sessions(event_id: str | None = None, booth_id: str | None = None):
        return db.query_presence_sessions(booth.db_path, event_id, booth_id)

    @app.get("/api/dashboard/known_ids")
    def api_dashboard_known_ids():
        return db.query_known_ids(booth.db_path)

    @app.post("/api/dashboard/delete_scope")
    def api_dashboard_delete_scope(payload: dict):
        scope_booth_id = (payload.get("booth_id") or "").strip() or None
        scope_event_id = (payload.get("event_id") or "").strip() or None
        if not scope_booth_id and not scope_event_id:
            raise HTTPException(400, "กรุณาระบุ booth_id หรือ event_id")
        db.delete_scope_data(booth.db_path, booth_id=scope_booth_id, event_id=scope_event_id)
        return {"ok": True}

    @app.get("/api/dashboard/export.xlsx")
    def api_dashboard_export(event_id: str | None = None, booth_id: str | None = None):
        content = build_workbook(booth.db_path, event_id, booth_id)
        scope = booth_id or event_id or "all"
        filename = f"mongdee-export-{scope}-{int(time.time())}.xlsx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app
