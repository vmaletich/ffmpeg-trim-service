import os
import uuid
import subprocess
import tempfile
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI(title="FFmpeg Trim Service")

# --- Старый вариант (на будущее). Можно оставить, не мешает ---
class TrimRequest(BaseModel):
    audio_url: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    scene_index: Optional[int] = None

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/trim")
async def trim(req: TrimRequest):
    if req.end <= req.start:
        raise HTTPException(status_code=400, detail="end must be > start")

    workdir = tempfile.mkdtemp(prefix="trim_")
    in_path = os.path.join(workdir, "input")
    out_name = f"scene_{req.scene_index if req.scene_index is not None else uuid.uuid4().hex}.mp3"
    out_path = os.path.join(workdir, out_name)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(req.audio_url, follow_redirects=True)
            r.raise_for_status()
            with open(in_path, "wb") as f:
                f.write(r.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"failed to download audio_url: {e}")

    cmd = [
        "ffmpeg", "-y",
        "-i", in_path,
        "-ss", str(req.start),
        "-to", str(req.end),
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", "128k",
        out_path
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=f"ffmpeg error: {p.stderr[-1500:]}")

    return FileResponse(out_path, media_type="audio/mpeg", filename=out_name)

# --- Вариант A: принимаем файл напрямую (то, что тебе нужно) ---
@app.post("/trim_upload")
async def trim_upload(
    file: UploadFile = File(...),
    start: float = Form(...),
    end: float = Form(...),
    scene_index: Optional[int] = Form(None),
):
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be > start")

    workdir = tempfile.mkdtemp(prefix="trim_")
    in_path = os.path.join(workdir, file.filename or "input.mp3")
    out_name = f"scene_{scene_index if scene_index is not None else uuid.uuid4().hex}.mp3"
    out_path = os.path.join(workdir, out_name)

    # Save uploaded file
    with open(in_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Trim with ffmpeg
    cmd = [
        "ffmpeg", "-y",
        "-i", in_path,
        "-ss", str(start),
        "-to", str(end),
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", "128k",
        out_path
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=f"ffmpeg error: {p.stderr[-1500:]}")

    return FileResponse(out_path, media_type="audio/mpeg", filename=out_name)
