"""
FaceFlow AI — FastAPI Application
Main entry point: mounts static files, registers routes, configures global error handling.
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.api import routes_health, routes_scan, routes_verify

# Setup logging before anything else
setup_logging()
logger = get_logger(__name__)

# ── Create app ───────────────────────────────────────────────
app = FastAPI(
    title="FaceFlow AI",
    description="Face identification, web discovery, and blockchain verification pipeline.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

# CORS — dev only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────
app.include_router(routes_health.router)
app.include_router(routes_scan.router)
app.include_router(routes_verify.router)

# ── Global exception handler — never expose stack traces ─────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
            },
        },
    )


# ── Startup: preload face model ───────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("FaceFlow AI starting — env=%s", settings.app_env)
    logger.info("Preloading InsightFace model...")
    try:
        from app.services.face_service import preload_model
        preload_model()
        logger.info("Face model ready.")
    except Exception as e:
        logger.error("Face model preload FAILED: %s", e)
        logger.error("The /api/scan endpoint will fail until the model downloads.")

    # Create temp dir
    os.makedirs("temp", exist_ok=True)


# ── Mount frontend LAST so it doesn't shadow API routes ───────
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
