import os
import time
import logging
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Set these in Render environment
VILLOUD_API_KEY = os.environ.get("VILLOUD_API_KEY")
VILLOUD_INGEST_URL = os.environ.get("VILLOUD_INGEST_URL")      # e.g. https://api.viloud.io/ingest
VILLOUD_STATUS_URL = os.environ.get("VILLOUD_STATUS_URL")      # e.g. https://api.viloud.io/ingest/status/
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")                    # optional

MAX_DOWNLOAD_TIMEOUT = 60 * 5    # 5 minutes
POLL_INTERVAL = 15               # seconds
MAX_POLLS = 60                   # poll up to ~15 minutes
MAX_ATTEMPTS = 3

def find_file_url_from_webhook(payload):
    def iter_values(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                yield from iter_values(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from iter_values(v)
        else:
            yield obj
    for v in iter_values(payload):
        if isinstance(v, str) and v.lower().startswith("http"):
            if any(ext in v.lower() for ext in [".mp4", ".mov", ".m4v", ".webm", ".avi", ".wmv"]):
                return v
    return None

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "invalid payload"}), 400

    entry_id = payload.get("EntryId") or payload.get("entryId") or payload.get("id") or "unknown"
    file_url = find_file_url_from_webhook(payload)
    if not file_url:
        app.logger.error("No file URL found in webhook for entry %s", entry_id)
        return jsonify({"status": "no_file_url"}), 200

    app.logger.info("Received webhook for entry %s, file_url: %s", entry_id, file_url)

    # Start synchronous processing for pilot
    success, detail = process_entry(entry_id, file_url, payload)
    status = "processing_started" if success else "error"
    return jsonify({"status": status, "detail": detail}), 200

def process_entry(entry_id, file_url, metadata):
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        try:
            app.logger.info("Download (attempt %s) for entry %s", attempts, entry_id)
            with requests.get(file_url, stream=True, timeout=MAX_DOWNLOAD_TIMEOUT) as r:
                r.raise_for_status()
                headers = {"Authorization": f"Bearer {VILLOUD_API_KEY}"} if VILLOUD_API_KEY else {}
                files = {"file": ("upload.mp4", r.raw, "application/octet-stream")}
                data = {
                    "title": metadata.get("EnterTheNameOfYourVideoSketch") or metadata.get("title") or "Uploaded Video",
                    "entryId": entry_id
                }
                app.logger.info("Uploading to Viloud ingest for entry %s", entry_id)
                resp = requests.post(VILLOUD_INGEST_URL, headers=headers, files=files, data=data, timeout=60*10)
                resp.raise_for_status()
                ingest_resp = resp.json()
                ingest_id = ingest_resp.get("ingestId") or ingest_resp.get("id") or ingest_resp.get("jobId")
                if not ingest_id:
                    app.logger.error("No ingest id returned from Viloud: %s", ingest_resp)
                    return False, "no_ingest_id"
                app.logger.info("Viloud ingest requested, ingest_id=%s", ingest_id)

            # Poll for ready
            for i in range(MAX_POLLS):
                time.sleep(POLL_INTERVAL)
                status_resp = requests.get(f"{VILLOUD_STATUS_URL}{ingest_id}", headers=headers, timeout=30)
                if status_resp.status_code != 200:
                    app.logger.warning("Viloud status check returned %s", status_resp.status_code)
                    continue
                sjson = status_resp.json()
                state = (sjson.get("status") or sjson.get("state") or "").lower()
                app.logger.info("Viloud status for %s: %s", ingest_id, state)
                if state in ["ready", "processed", "completed"]:
                    video_id = sjson.get("videoId") or sjson.get("id")
                    app.logger.info("Video ready for entry %s; video_id=%s", entry_id, video_id)
                    # TODO: persist mapping and notify contestant for payment
                    return True, "ready"
                if state in ["error", "failed"]:
                    app.logger.error("Viloud ingest failed for %s: %s", ingest_id, sjson)
                    return False, "viloud_failed"
            app.logger.error("Viloud processing timed out for ingest %s", ingest_id)
            return False, "viloud_timeout"

        except Exception as e:
            app.logger.exception("Processing error for entry %s: %s", entry_id, str(e))
            if attempts < MAX_ATTEMPTS:
                backoff = 5 * attempts
                app.logger.info("Retrying after %s seconds", backoff)
                time.sleep(backoff)
                continue
            else:
                # final failure
                # Optionally: send admin notification here
                return False, str(e)
    return False, "max_attempts_exceeded"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

    Replace or confirm requirements.txt

    If requirements.txt exists, open and edit it to exactly:

Flask==2.2.5
requests==2.31.0
gunicorn==20.1.0

    Commit the change.

    Set the Render start command

    In your Render service Settings → Start Command set: gunicorn app:app --bind 0.0.0.0:$PORT --workers 4

    Add Render environment variables (Dashboard → Environment)

    VILLOUD_API_KEY = (your Viloud API key)
    VILLOUD_INGEST_URL = (Viloud ingest endpoint)
    VILLOUD_STATUS_URL = (Viloud ingest status base URL)
    ADMIN_EMAIL = your email (optional)
