from __future__ import annotations

import json
import queue
import time

from flask import Blueprint, Response, jsonify, request

from ..services.runner import COMMANDS, manager, preflight

bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


@bp.post("")
def create_job():
    data = request.get_json(force=True)
    script = (data.get("script") or "").strip()
    command = data.get("command") or "build"
    provider = data.get("provider")
    limit = data.get("limit")
    force = bool(data.get("force"))

    if not script:
        return jsonify({"error": "missing 'script'"}), 400
    if command not in COMMANDS:
        return jsonify({"error": f"command must be one of {COMMANDS}"}), 400
    if provider not in (None, "dryrun", "minimax"):
        return jsonify({"error": "provider must be dryrun or minimax"}), 400

    import os

    if not provider:
        provider = os.environ.get("TTS_PROVIDER", "dryrun")

    if command in ("tts", "build"):
        errors = preflight(provider)
        if errors:
            return jsonify({"error": "; ".join(errors)}), 400

    if limit is not None:
        try:
            limit = int(limit)
            if limit <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "limit must be a positive integer"}), 400

    running = manager.current_running()
    job = manager.submit(script, command, provider, limit, force)
    return jsonify({"job": job.to_dict(), "queued_behind": running.id if running else None}), 201


@bp.get("")
def list_jobs():
    return jsonify([j.to_dict() for j in manager.recent(30)])


@bp.get("/<job_id>")
def get_job(job_id: str):
    job = manager.get(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job.to_dict(include_logs=True))


@bp.post("/<job_id>/cancel")
def cancel_job(job_id: str):
    ok = manager.cancel(job_id)
    if not ok:
        return jsonify({"error": "job not cancellable (not queued/running, or not found)"}), 400
    return jsonify({"cancelled": job_id})


@bp.get("/<job_id>/events")
def job_events(job_id: str):
    q = manager.subscribe(job_id)
    if q is None:
        return jsonify({"error": "job not found"}), 404

    def generate():
        try:
            while True:
                try:
                    ev = q.get(timeout=15)
                except queue.Empty:
                    job = manager.get(job_id)
                    if job is not None and job.status in ("done", "failed", "cancelled"):
                        break
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev.get("kind") == "job_done":
                    break
                if ev.get("kind") == "snapshot":
                    job = manager.get(job_id)
                    if job is not None and job.status in ("done", "failed", "cancelled"):
                        end = {"kind": "job_done", "status": job.status, "ts": time.time(), "job_id": job_id}
                        yield f"data: {json.dumps(end, ensure_ascii=False)}\n\n"
                        break
        finally:
            manager.unsubscribe(job_id, q)

    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
