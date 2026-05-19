from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .color_recipe import analyze_images


app = FastAPI(title="Color Recipe API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    source: UploadFile = File(...),
    reference: UploadFile = File(...),
    strength: float = Form(0.7),
    lut_size: int = Form(17),
) -> dict:
    if not source.content_type or not source.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="source must be an image")
    if not reference.content_type or not reference.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="reference must be an image")

    source_bytes = await source.read()
    reference_bytes = await reference.read()
    if not source_bytes or not reference_bytes:
        raise HTTPException(status_code=400, detail="both source and reference images are required")

    try:
        return analyze_images(source_bytes, reference_bytes, strength=strength, lut_size=lut_size)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="image analysis failed: %s" % exc) from exc
