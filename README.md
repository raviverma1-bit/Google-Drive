# Drive Folder Bulk Downloader (Render deployment)

A small Flask app with a one-click "Start Download" button that pulls
all files from the configured Google Drive folder links (they must be
public / "anyone with the link"), zips them, and lets you download the zip.

## Deploy on Render

1. Push this folder to a GitHub repo (or use Render's "Deploy from a
   public Git repo" and point it at wherever you host these files).
2. In the Render dashboard: **New +** → **Web Service** → connect the repo.
3. Render should auto-detect `render.yaml`. If not, set manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --timeout 600`
   - Environment: Python 3
4. Deploy. Once live, open the service URL — you'll see the download page.

## Using it

1. Click **Start Download**.
2. Watch the progress bar and live log as it works through each folder.
3. When it says "done", click **Download ZIP**.

## Important limits

- **Ephemeral disk**: Render web services don't guarantee persistent
  storage across restarts/redeploys. Download the zip promptly after
  each run — don't treat this as long-term storage.
- **Free/starter plans spin down** after inactivity, which can interrupt
  a long job. For a large batch of folders, consider:
  - A paid, always-on instance, or
  - Converting this into a Render **Background Worker** or **Cron Job**
    that uploads results somewhere persistent (e.g. S3) instead of
    serving a local zip.
- **Only works for public folders.** If a folder isn't shared as
  "anyone with the link," gdown will fail for it — you'll see the
  failure in the live log, and it'll still be counted as "completed"
  so the job doesn't hang.
- To change which folders it pulls, edit the `FOLDER_LINKS` list at the
  top of `app.py` and redeploy.

## Running locally first (optional, recommended)

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser.
