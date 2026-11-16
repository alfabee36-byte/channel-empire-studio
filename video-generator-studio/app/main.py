from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import edge_tts
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
for directory in (UPLOAD_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "12"))
SADTALKER_DIR = os.getenv("SADTALKER_DIR", "").strip()
SADTALKER_PYTHON = os.getenv("SADTALKER_PYTHON", "").strip()
jobs: dict[str, dict[str, Any]] = {}

app = FastAPI(title="AI Video Generator Studio", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home():
    return (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "sadtalker_configured": bool(SADTALKER_DIR and (Path(SADTALKER_DIR) / "inference.py").exists()),
        "speech": "Edge TTS (internet required)",
    }


async def create_speech(text: str, voice: str, target: Path):
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(str(target))


def run_ffmpeg(image: Path, audio: Path, output: Path):
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(image), "-i", str(audio),
        "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac",
        "-b:a", "192k", "-pix_fmt", "yuv420p", "-shortest",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-movflags", "+faststart", str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def run_sadtalker(image: Path, audio: Path, job_dir: Path) -> Path:
    repo = Path(SADTALKER_DIR)
    inference = repo / "inference.py"
    if not inference.exists():
        raise RuntimeError("SadTalker belum dikonfigurasi: inference.py tidak ditemukan.")
    python_bin = SADTALKER_PYTHON or shutil.which("python") or "python"
    result_dir = job_dir / "sadtalker"
    result_dir.mkdir(exist_ok=True)
    cmd = [
        python_bin, str(inference), "--driven_audio", str(audio),
        "--source_image", str(image), "--result_dir", str(result_dir),
        "--still", "--preprocess", "full",
    ]
    subprocess.run(cmd, cwd=str(repo), check=True, capture_output=True, text=True)
    videos = sorted(result_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        raise RuntimeError("SadTalker selesai tetapi tidak menghasilkan MP4.")
    return videos[0]


async def process_job(job_id: str, image: Path, script: str, language: str, voice: str, avatar_mode: str):
    job_dir = DATA_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    audio = job_dir / "voice.mp3"
    output = OUTPUT_DIR / f"{job_id}.mp4"
    try:
        jobs[job_id].update(status="processing", progress=10, message="Membuat suara...")
        await create_speech(script, voice, audio)
        jobs[job_id].update(progress=45, message="Merender video...")
        if avatar_mode == "talking":
            if not SADTALKER_DIR:
                raise RuntimeError("Mode Talking Photo memerlukan SadTalker + model checkpoints. Isi SADTALKER_DIR di .env. Pilih mode Narrated Portrait untuk hasil tanpa lip-sync.")
            generated = await asyncio.to_thread(run_sadtalker, image, audio, job_dir)
            shutil.copy2(generated, output)
        else:
            await asyncio.to_thread(run_ffmpeg, image, audio, output)
        jobs[job_id].update(status="completed", progress=100, message="Video siap diunduh.", download_url=f"/api/jobs/{job_id}/download")
    except Exception as exc:
        jobs[job_id].update(status="failed", progress=0, message=str(exc)[:700])


@app.post("/api/generate")
async def generate(
    photo: UploadFile = File(...),
    script: str = Form(...),
    language: str = Form("id"),
    voice: str = Form("id-ID-ArdiNeural"),
    avatar_mode: str = Form("narrated"),
):
    if not shutil.which("ffmpeg"):
        raise HTTPException(500, "FFmpeg belum terpasang. Jalankan: sudo apt-get update && sudo apt-get install -y ffmpeg")
    if not script.strip() or len(script) > 5000:
        raise HTTPException(400, "Naskah wajib diisi (maksimal 5.000 karakter).")
    if language not in {"id", "en"} or avatar_mode not in {"narrated", "talking"}:
        raise HTTPException(400, "Pilihan bahasa atau mode tidak valid.")
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if photo.content_type not in allowed:
        raise HTTPException(400, "Gunakan foto JPG, PNG, atau WEBP.")
    content = await photo.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Ukuran foto maksimal {MAX_UPLOAD_MB} MB.")
    job_id = uuid.uuid4().hex
    image_path = UPLOAD_DIR / f"{job_id}{allowed[photo.content_type]}"
    image_path.write_bytes(content)
    jobs[job_id] = {"status": "queued", "progress": 0, "message": "Menunggu proses..."}
    asyncio.create_task(process_job(job_id, image_path, script.strip(), language, voice, avatar_mode))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job tidak ditemukan. Server mungkin baru saja restart.")
    return {"job_id": job_id, **jobs[job_id]}


@app.get("/api/jobs/{job_id}/download")
async def download(job_id: str):
    if job_id not in jobs or jobs[job_id].get("status") != "completed":
        raise HTTPException(404, "Video belum tersedia.")
    path = OUTPUT_DIR / f"{job_id}.mp4"
    if not path.exists():
        raise HTTPException(404, "File video tidak ditemukan.")
    return FileResponse(path, media_type="video/mp4", filename="ai-video.mp4")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=os.getenv("APP_HOST", "0.0.0.0"), port=int(os.getenv("APP_PORT", "8000")), reload=True)
