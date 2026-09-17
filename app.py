#!/usr/bin/env python3
"""
Render-deployable web app that bulk-downloads a list of public
("anyone with the link") Google Drive folders using gdown, zips the
result, and serves it for download.

Deploy on Render as a "Web Service":
  - Build command:  pip install -r requirements.txt
  - Start command:  gunicorn app:app

NOTE: Render's free/starter instances have ephemeral disk and can spin
down after inactivity. Download the zip promptly after the job finishes;
don't rely on this as permanent storage. For very large or long-running
jobs, prefer a paid instance or a Render Background Worker/Cron Job.
"""

import os
import re
import threading
import shutil
import zipfile
from datetime import datetime

from flask import Flask, jsonify, send_file, request, render_template_string

try:
    import gdown
except ImportError:
    gdown = None

app = Flask(__name__)

# ----------------------------------------------------------------------------
# Folder links — edit this list as needed
# ----------------------------------------------------------------------------
FOLDER_LINKS = [
    "https://drive.google.com/drive/folders/1BYctOnok9PaXFIAz-eh42EPNIOH5882d",
    "https://drive.google.com/drive/folders/1SfjQsgbIoNHTdggX2_kXFtOzkQ91gvZX",
    "https://drive.google.com/drive/folders/1ciwqEVpfTHgBjOziGqwDj2FD0X7izpJz",
    "https://drive.google.com/drive/folders/1j0RjH8-Ti9WpPi-pSNcpvSu1RKzQZ0Pc",
    "https://drive.google.com/drive/folders/18XKX82n2UZwgVPZny5dyf02PCkzULZLZ",
    "https://drive.google.com/drive/folders/1DdSr3sPyHEvO-yGGjnnKKFwpFuRY7zWV",
    "https://drive.google.com/drive/folders/11JFCh5mcV4pwPMLFQeGkHUOzKdWLRmP3",
    "https://drive.google.com/drive/folders/141dk3B47wzgvljpHHoDrl3KKpEjFzAZ1",
    "https://drive.google.com/drive/folders/1tpZ6NwKKwaYKocPK__caBskTQE9DL9gR",
    "https://drive.google.com/drive/folders/1JyMT6eUR1Vo2tAT7sfTrPbSAOtF22CyF",
    "https://drive.google.com/drive/folders/15GdZeE1IgvwQ98QtEfcgyuMoyV1mfiYn",
    "https://drive.google.com/drive/folders/1q1My60SufRbUzM8xCw6Kd4hAks94qqe3",
    "https://drive.google.com/drive/folders/1-mIfjAfw2t_aABnsw6UCTqUZm479wp9k",
    "https://drive.google.com/drive/folders/1uabMMhB0CJgx7rwwFKugp6l-SCvmtZIz",
    "https://drive.google.com/drive/folders/1OFNd2PGTRvWgOGJ3eS6wC_6iouCj3DFo",
    "https://drive.google.com/drive/folders/1peQP3sT5Ih3sILJKw_pertnRVg1kn8nl",
    "https://drive.google.com/drive/folders/1dKw7QEG8Re0fgqf15TM63iHe1x6FqE1N",
    "https://drive.google.com/drive/folders/1McTwfHk1DVYk3EhTz6zCJA9h7a2M0x7Y",
    "https://drive.google.com/drive/folders/1QHRe31hAbeKpp-RRlKmW6oWdIlrV6W-l",
    "https://drive.google.com/drive/folders/1Nn_dxKjIRVCO2d1pS_bvW3FeQvwoE-Z_",
    "https://drive.google.com/drive/folders/1HnoSYN3Mwg5N3LhHDTkjOPayQu40RfUZ",
    "https://drive.google.com/drive/folders/1IQDU-QlOiT2jCUkouFxsW8_VdhyPfJTb",
    "https://drive.google.com/drive/folders/12RQ_WYn0nxUthG_16dC2IcHoXwZz6Qwz",
    "https://drive.google.com/drive/folders/1K5u44-nnFtPergmYQvTcf1bJpngWC-GL",
    "https://drive.google.com/drive/folders/1lwVC45Z20F_lsmIcOvVZRwNuOP_BWr19",
    "https://drive.google.com/drive/folders/16hYvatqcV8XYBxPcWPgMyjYQLpN6C0fD",
    "https://drive.google.com/drive/folders/1yHvAE4Xe-jxiSuTDdwDM3Ac08fjn8zBB",
    "https://drive.google.com/drive/folders/1Cd_pirBFMlzEstHX1JVVAmIuoA7eWRIl",
    "https://drive.google.com/drive/folders/1H53hhINSzO8MSu06C9qe0Eg3fdTbf8zN",
    "https://drive.google.com/drive/folders/1lhQ89tXe52qS8NifS5Uf_guni8--RecS",
    "https://drive.google.com/drive/folders/1wj9EKZZW0_0HmI2qJSZkhTV5Aa27zCV6",
    "https://drive.google.com/drive/folders/18SjA82xRiOiaD22sZWGwzQlRKG_HTpTL",
    "https://drive.google.com/drive/folders/1_TExElnJA9dRQQ6Rm8DTrvzheR3a_w8z",
    "https://drive.google.com/drive/folders/1C40Iw1IC2aYu5GYt0CAF5phx3OyuuCDt",
    "https://drive.google.com/drive/folders/1hgCv-oCP0AU3Zk5EDgZRAl1azFS-0FVQ",
    "https://drive.google.com/drive/folders/1PfldUqtJ2m9F_sGO2GIAzrWn3uE33Kz1",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "drive_downloads")
ZIP_PATH = os.path.join(BASE_DIR, "drive_downloads.zip")

# Simple in-memory job state (fine for a single-instance Render service)
state = {
    "status": "idle",       # idle | running | zipping | done | error
    "total": len(FOLDER_LINKS),
    "completed": 0,
    "current_folder": None,
    "log": [],
    "zip_ready": False,
    "started_at": None,
    "finished_at": None,
}
state_lock = threading.Lock()


def log(msg: str):
    line = f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}"
    with state_lock:
        state["log"].append(line)
        state["log"] = state["log"][-500:]  # keep it bounded
    print(line, flush=True)


def extract_folder_id(url: str) -> str:
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"Could not find a folder ID in: {url}")
    return match.group(1)


def run_job():
    if gdown is None:
        with state_lock:
            state["status"] = "error"
        log("gdown is not installed. Check requirements.txt / build logs.")
        return

    with state_lock:
        state["status"] = "running"
        state["completed"] = 0
        state["log"] = []
        state["zip_ready"] = False
        state["started_at"] = datetime.utcnow().isoformat()
        state["finished_at"] = None

    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    for link in FOLDER_LINKS:
        folder_id = extract_folder_id(link)
        dest = os.path.join(DOWNLOAD_DIR, folder_id)
        os.makedirs(dest, exist_ok=True)

        with state_lock:
            state["current_folder"] = folder_id

        log(f"Downloading folder {folder_id} ...")
        try:
            gdown.download_folder(url=link, output=dest, quiet=True, use_cookies=False)
            log(f"  OK: {folder_id}")
        except Exception as e:
            log(f"  FAILED: {folder_id} -> {e}")

        with state_lock:
            state["completed"] += 1

    log("All folders processed. Creating zip archive ...")
    with state_lock:
        state["status"] = "zipping"

    if os.path.exists(ZIP_PATH):
        os.remove(ZIP_PATH)

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(DOWNLOAD_DIR):
            for f in files:
                full_path = os.path.join(root, f)
                arcname = os.path.relpath(full_path, DOWNLOAD_DIR)
                zf.write(full_path, arcname)

    log("Zip archive ready.")
    with state_lock:
        state["status"] = "done"
        state["zip_ready"] = True
        state["finished_at"] = datetime.utcnow().isoformat()


PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Drive Folder Bulk Downloader</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 16px; }
    button { padding: 10px 18px; font-size: 15px; cursor: pointer; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    #log { background: #111; color: #0f0; font-family: monospace; font-size: 12px;
           padding: 12px; height: 320px; overflow-y: auto; white-space: pre-wrap; border-radius: 6px; }
    .bar-bg { background: #eee; border-radius: 6px; height: 18px; overflow: hidden; margin: 12px 0; }
    .bar { background: #4caf50; height: 100%; width: 0%; transition: width 0.3s; }
    a.download { display: inline-block; margin-top: 12px; }
  </style>
</head>
<body>
  <h2>Drive Folder Bulk Downloader</h2>
  <p>{{ total }} folders configured. Click start to download and zip them all.</p>
  <button id="startBtn" onclick="start()">Start Download</button>
  <div class="bar-bg"><div class="bar" id="bar"></div></div>
  <div id="statusText">Idle.</div>
  <a class="download" id="dlLink" href="/download" style="display:none;">⬇ Download ZIP</a>
  <h3>Log</h3>
  <div id="log"></div>

<script>
function start() {
  document.getElementById('startBtn').disabled = true;
  fetch('/start', { method: 'POST' }).then(poll);
}
function poll() {
  fetch('/status').then(r => r.json()).then(s => {
    const pct = s.total ? Math.round((s.completed / s.total) * 100) : 0;
    document.getElementById('bar').style.width = pct + '%';
    document.getElementById('statusText').textContent =
      `Status: ${s.status} — ${s.completed}/${s.total} folders` +
      (s.current_folder ? ` (current: ${s.current_folder})` : '');
    document.getElementById('log').textContent = s.log.join('\\n');
    document.getElementById('log').scrollTop = document.getElementById('log').scrollHeight;
    if (s.zip_ready) {
      document.getElementById('dlLink').style.display = 'inline-block';
    }
    if (s.status === 'running' || s.status === 'zipping') {
      setTimeout(poll, 1500);
    } else {
      document.getElementById('startBtn').disabled = false;
    }
  });
}
window.onload = poll;
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE, total=len(FOLDER_LINKS))


@app.route("/start", methods=["POST"])
def start():
    with state_lock:
        if state["status"] in ("running", "zipping"):
            return jsonify({"ok": False, "message": "Job already running"}), 409
    thread = threading.Thread(target=run_job, daemon=True)
    thread.start()
    return jsonify({"ok": True})


@app.route("/status")
def status():
    with state_lock:
        return jsonify(dict(state))


@app.route("/download")
def download():
    if not os.path.exists(ZIP_PATH):
        return "Zip not ready yet.", 404
    return send_file(ZIP_PATH, as_attachment=True, download_name="drive_downloads.zip")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
