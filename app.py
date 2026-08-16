import os
import re
import uuid
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
JOBS_DIR = BASE_DIR / "jobs"
JOBS_DIR.mkdir(exist_ok=True)

SEGMENT_SECONDS = 40

# In-memory job status tracker: {job_id: {"status": ..., "message": ..., "zip": ...}}
JOBS = {}


def is_valid_youtube_url(url: str) -> bool:
    pattern = r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]+"
    return bool(re.match(pattern, url.strip()))


def run_job(job_id: str, url: str):
    job_dir = JOBS_DIR / job_id
    raw_dir = job_dir / "raw"
    parts_dir = job_dir / "parts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parts_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Download video with yt-dlp
        JOBS[job_id] = {"status": "downloading", "message": "Downloading video..."}
        output_template = str(raw_dir / "source.%(ext)s")
        download_cmd = [
            "yt-dlp",
            "-f", "mp4/best",
            "-o", output_template,
            url,
        ]
        result = subprocess.run(download_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            JOBS[job_id] = {
                "status": "error",
                "message": f"Download failed: {result.stderr[-500:]}",
            }
            return

        # Find the downloaded file
        downloaded_files = list(raw_dir.glob("source.*"))
        if not downloaded_files:
            JOBS[job_id] = {"status": "error", "message": "No file was downloaded."}
            return
        source_file = downloaded_files[0]

        # 2. Split into 40-second segments with ffmpeg
        JOBS[job_id] = {"status": "splitting", "message": "Splitting video into parts..."}
        segment_pattern = str(parts_dir / "part_%03d.mp4")
        split_cmd = [
            "ffmpeg",
            "-i", str(source_file),
            "-c", "copy",
            "-map", "0",
            "-segment_time", str(SEGMENT_SECONDS),
            "-f", "segment",
            "-reset_timestamps", "1",
            segment_pattern,
        ]
        result = subprocess.run(split_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Fallback: re-encode if stream copy fails (e.g. non-keyframe-aligned cuts)
            split_cmd_reencode = [
                "ffmpeg",
                "-i", str(source_file),
                "-map", "0",
                "-segment_time", str(SEGMENT_SECONDS),
                "-f", "segment",
                "-reset_timestamps", "1",
                segment_pattern,
            ]
            result = subprocess.run(split_cmd_reencode, capture_output=True, text=True)
            if result.returncode != 0:
                JOBS[job_id] = {
                    "status": "error",
                    "message": f"Splitting failed: {result.stderr[-500:]}",
                }
                return

        # 3. Zip the parts folder
        JOBS[job_id] = {"status": "zipping", "message": "Packaging your download..."}
        zip_path = job_dir / "video_parts.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for part_file in sorted(parts_dir.glob("part_*.mp4")):
                zf.write(part_file, arcname=part_file.name)

        # Clean up raw download to save space
        shutil.rmtree(raw_dir, ignore_errors=True)

        JOBS[job_id] = {
            "status": "done",
            "message": "Ready for download.",
            "zip": f"/download/{job_id}",
        }

    except Exception as e:
        JOBS[job_id] = {"status": "error", "message": str(e)}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()

    if not url or not is_valid_youtube_url(url):
        return jsonify({"error": "Please enter a valid YouTube URL."}), 400

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "queued", "message": "Queued..."}

    thread = threading.Thread(target=run_job, args=(job_id, url), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job id"}), 404
    return jsonify(job)


@app.route("/download/<job_id>")
def download(job_id):
    job_dir = JOBS_DIR / job_id
    zip_path = job_dir / "video_parts.zip"
    if not zip_path.exists():
        return "File not found or not ready yet.", 404
    return send_from_directory(job_dir, "video_parts.zip", as_attachment=True,
                                download_name=f"video_parts_{job_id}.zip")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
