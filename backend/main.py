"""Aplikasi FastAPI ParkSense. Jalankan: uvicorn backend.main:app --reload --port 8000"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import db, errors
from .routes import stub

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.conn()  # pastikan database dan seed siap
    yield


app = FastAPI(
    title="ParkSense API",
    version="0.1.0",
    description="Spesifikasi antarmuka layanan REST API ParkSense (Bagian 2.3).",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
errors.install(app)

api = APIRouter(prefix="/api/v1")
# Endpoint asli didaftarkan di atas baris stub; stub paling akhir (akan dihapus).
api.include_router(stub.router)
app.include_router(api)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")
