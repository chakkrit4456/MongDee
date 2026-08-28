"""FastAPI app: everything the desktop app does, reachable from any browser
on the same machine or the local network — booth view (live streams + AI
Product Assistant + readiness check + health alerts), Dashboard, and AI
Trainer. See web_server.py for the CLI entrypoint that builds this app.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import database as db
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

    @app.post("/api/ask")
    def api_ask(payload: dict):
        question = (payload.get("question") or "").strip()
        if not question:
            raise HTTPException(400, "กรุณาระบุคำถาม")
        return booth.ask(question)

    @app.post("/api/readiness")
    def api_readiness():
        return booth.run_readiness()

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
        booth.catalog.add_product(key, name, payload.get("tagline", ""), payload.get("description", ""))
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

    return app
