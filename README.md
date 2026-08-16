# Splitreel — split a YouTube video into 40-second parts

A small Flask website: paste a YouTube link, the server downloads the video
with `yt-dlp`, cuts it into 40-second segments with `ffmpeg`, zips the parts,
and gives you a download link.

⚠️ **Only run this on videos you own or have explicit rights to download and
redistribute.** Downloading other people's YouTube videos generally violates
YouTube's Terms of Service and can infringe copyright.

## 1. Requirements

- Python 3.9+
- `ffmpeg` installed and on your PATH
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: download from ffmpeg.org and add it to PATH

## 2. Setup

```bash
cd yt-splitter
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Run it

```bash
python app.py
```

Open **http://localhost:5000** in your browser.

## 4. How it works

1. You paste a YouTube URL and click "Split it."
2. `POST /submit` validates the URL and starts a background job (thread).
3. The frontend polls `GET /status/<job_id>` every 1.5s for progress:
   `downloading` → `splitting` → `zipping` → `done`.
4. The server:
   - downloads the video with `yt-dlp` into `jobs/<job_id>/raw/`
   - splits it into 40-second `.mp4` chunks with `ffmpeg`'s `segment` muxer,
     using stream copy first (fast, no re-encode) and falling back to
     re-encoding only if the fast path fails
   - zips all parts into `jobs/<job_id>/video_parts.zip`
5. `GET /download/<job_id>` serves the zip file.

## 5. Deploying to Render (free tier)

The repo includes a `Dockerfile` (with `ffmpeg` pre-installed) and a
`render.yaml`, so deployment is mostly automatic.

1. **Push this project to a GitHub repo.**
   ```bash
   cd yt-splitter
   git init
   git add .
   git commit -m "Initial commit"
   ```
   Create a new repo on GitHub, then:
   ```bash
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git branch -M main
   git push -u origin main
   ```

2. **On [render.com](https://render.com)**, sign up/log in, then click
   **New +** → **Web Service**.

3. Connect your GitHub account and select the repo.

4. Render should auto-detect `render.yaml` and `Dockerfile`. If asked:
   - **Environment**: Docker
   - **Plan**: Free
   - Leave build/start commands blank (the Dockerfile handles it).

5. Click **Create Web Service**. First build takes a few minutes (installing
   ffmpeg + Python deps into the image).

6. Once deployed, Render gives you a public URL like
   `https://splitreel.onrender.com` — open that instead of localhost.

### Free tier limitations to know about

- **Sleep on inactivity**: the free instance spins down after ~15 minutes of
  no traffic. The next request will take 30–60 seconds to wake it back up.
- **Ephemeral disk**: free tier storage is not persistent across deploys/
  restarts — fine for this app since jobs are meant to be temporary, but
  don't expect old zip files to survive a redeploy.
- **512MB RAM / limited CPU**: works fine for short/medium videos. Long or
  high-resolution videos may run out of memory or time out.
- **Single worker**: the Dockerfile runs gunicorn with `-w 1` on purpose,
  since job status is tracked in memory — multiple workers wouldn't share
  that state. This keeps things correct but means only one video is
  processed at a time.

## 6. Notes & things you may want to change

- **Segment length**: change `SEGMENT_SECONDS` in `app.py`.
- **Job cleanup**: finished jobs are left in `jobs/`. For a real deployment,
  add a scheduled task (e.g. `cron` or `APScheduler`) to delete job folders
  older than a few hours.
- **Concurrency**: jobs run in simple Python threads with in-memory status.
  Fine for personal/single-user use. For multiple simultaneous users in
  production, swap this for a task queue (Celery + Redis, or RQ) and
  persistent job storage.
- **Video length limits**: there's currently no cap on video length or file
  size — consider adding one (e.g. reject videos over N minutes) if you're
  exposing this publicly.
- **Deployment**: works as-is on any host with Python + ffmpeg (a small VPS,
  Railway, Render, Fly.io). Make sure the host allows outbound network
  access and has enough disk space for temporary video files.
