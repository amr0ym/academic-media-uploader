
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request, abort

app = Flask(__name__)

API_TOKEN = os.environ.get("BRIDGE_API_TOKEN", "")
jobs = {}
jobs_lock = threading.Lock()

ALLOWED_OPERATIONS = {
    "record_youtube",
    "drive_transfer",
    "telegram_transfer",
}


def authorized():
    token = request.headers.get("Authorization", "")
    expected = f"Bearer {API_TOKEN}"

    return (
        bool(API_TOKEN)
        and secrets.compare_digest(token, expected)
    )


def now():
    return datetime.now(timezone.utc).isoformat()


@app.before_request
def check_auth():
    if request.path == "/health":
        return

    if not authorized():
        abort(401)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/jobs")
def create_job():
    data = request.get_json(silent=True) or {}
    operation = data.get("operation")

    if operation not in ALLOWED_OPERATIONS:
        return jsonify({"error": "Unsupported operation"}), 400

    job = {
        "id": str(uuid.uuid4()),
        "operation": operation,
        "status": "queued",
        "created_at": now(),
        "message": "Waiting for a connected worker",
    }

    with jobs_lock:
        jobs[job["id"]] = job

    return jsonify(job), 202


@app.get("/jobs")
def list_jobs():
    with jobs_lock:
        return jsonify(list(jobs.values()))


@app.get("/jobs/<job_id>")
def get_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(job)


@app.get("/")
def index():
    return jsonify({
        "service": "Academic Media Bridge",
        "status": "running",
        "worker_connected": False,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
