"""ZENTO COURIER API + static frontend."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal
from app.bootstrap import ensure_admin
from app.routers import admin, auth, dashboard, parcels, pricing, rider, tracking

log = logging.getLogger("zento")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        ensure_admin()
    except Exception:  # never block startup (e.g. migrations not applied yet)
        log.exception("Admin bootstrap failed")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(lifespan=lifespan,
        title="ZENTO COURIER API", version="1.0.0",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None, openapi_url=None if settings.is_production else "/api/openapi.json",
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            msg = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
            errors.append({"field": ".".join(loc), "message": msg})
        return JSONResponse(status_code=422, content={"detail": "Some details need fixing.", "errors": errors})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})

    @app.get("/api/health", tags=["meta"])
    def health():
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok"}

    for module in (auth, pricing, parcels, tracking, dashboard, admin, rider):
        app.include_router(module.router, prefix="/api")

    @app.get("/admin", include_in_schema=False)
    def admin_page():
        return FileResponse(FRONTEND_DIR / "admin" / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/rider", include_in_schema=False)
    def rider_page():
        return FileResponse(FRONTEND_DIR / "rider" / "index.html", headers={"Cache-Control": "no-cache"})

    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
