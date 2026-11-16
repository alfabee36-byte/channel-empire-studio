# AI Video Generator Studio

A self-hostable, bilingual (Bahasa Indonesia / English) photo-to-video studio.

## What works in this starter
- Upload a portrait photo and enter a script in Indonesian or English.
- Generate speech with Edge TTS (free-to-use online speech service; internet required).
- Render an MP4 with the portrait, audio, and optional subtitle burn-in using FFmpeg.
- Optional real talking-head lip-sync through a locally installed SadTalker checkout and its model checkpoints.
- Jobs are processed in the background and their status can be polled from the browser.

**Important:** without SadTalker configured, the app creates a narrated portrait video (still image + speech), not animated lip-sync. Actual avatar animation needs compatible model weights and preferably a GPU. No API key is required for the default speech/render path, but Edge TTS depends on an external service and may change its availability/terms.

## Requirements
- Python 3.11+
- FFmpeg installed and available on PATH
- Internet access for Edge TTS
- Optional: GPU-enabled environment and SadTalker model weights for lip-sync

## Run in GitHub Codespaces
1. Open this repository in GitHub Codespaces.
2. In the terminal:
   ```bash
   cd video-generator-studio
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   python -m app.main
   ```
3. Open the forwarded port **8000** from the Ports tab.
4. Upload a portrait (JPG/PNG), select language and voice, enter a script, then click Generate.
5. Wait for the job to finish and use Download MP4.

## Optional SadTalker lip-sync
1. Clone SadTalker separately and install its own documented dependencies/checkpoints:
   ```bash
   git clone https://github.com/OpenTalker/SadTalker.git
   ```
2. Configure `SADTALKER_DIR=/workspaces/SadTalker` in `.env` (adjust path).
3. Ensure the SadTalker Python environment and checkpoints are installed. The app invokes its `inference.py` with the configured Python executable.
4. Restart this app. Jobs will attempt talking-head generation; if unavailable or it fails, the job reports the error rather than silently claiming lip-sync.

Set `SADTALKER_PYTHON` to the Python executable in the SadTalker environment if it differs from the app's interpreter.

## Configuration
See `.env.example`. Uploaded photos, audio, and rendered videos are stored under `data/`; do not commit this folder. Use only photos and voices you have rights and consent to use. Avoid impersonation or misleading viewers.

## API
- `GET /` — studio UI
- `GET /api/health` — dependency/configuration status
- `POST /api/generate` — multipart photo + script + options; returns a job ID
- `GET /api/jobs/{job_id}` — job progress
- `GET /api/jobs/{job_id}/download` — completed MP4

## Limitations / next production steps
This is a runnable MVP, not a hosted HeyGen replacement. Codespaces is a development environment and is not a reliable always-on GPU renderer. Add authentication, per-user storage, upload quotas, job persistence/queueing, moderation, and a dedicated GPU worker before exposing it publicly.
