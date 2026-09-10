from __future__ import annotations

import re
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from ..services.runner import AUDIO

bp = Blueprint("assets", __name__, url_prefix="/api/assets")

AUDIO_KINDS = ("music", "sfx")
EXT_OK = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma"}
SAFE_NAME_RE = re.compile(r"^[\w\-.\u4e00-\u9fff ]+$")
WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _duration_of(path: Path) -> float | None:
    try:
        from pydub import AudioSegment

        return round(len(AudioSegment.from_file(path)) / 1000, 1)
    except Exception:  # noqa: BLE001
        return None


def _dir_for(kind: str) -> Path:
    if kind not in AUDIO_KINDS:
        raise ValueError(f"kind must be one of {AUDIO_KINDS}")
    d = AUDIO / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


@bp.get("/<kind>")
def list_assets(kind: str):
    try:
        d = _dir_for(kind)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    out = []
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        out.append(
            {
                "name": p.name,
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
                "duration": _duration_of(p) if p.suffix.lower() in EXT_OK else None,
            }
        )
    return jsonify(out)


@bp.post("/<kind>")
def upload_asset(kind: str):
    try:
        d = _dir_for(kind)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if "file" not in request.files:
        return jsonify({"error": "no file part in request"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "empty filename"}), 400
    name = Path(f.filename).name
    if not SAFE_NAME_RE.match(name):
        return jsonify({"error": f"unsafe filename: {name}"}), 400
    if Path(name).stem.upper() in WIN_RESERVED:
        return jsonify({"error": f"reserved device name on Windows: {name}"}), 400
    if Path(name).suffix.lower() not in EXT_OK:
        return jsonify({"error": f"unsupported audio type, allowed: {sorted(EXT_OK)}"}), 400
    dest = d / name
    f.save(dest)
    return jsonify({"name": name, "size": dest.stat().st_size, "saved": True}), 201


@bp.delete("/<kind>/<path:name>")
def delete_asset(kind: str, name: str):
    try:
        d = _dir_for(kind)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    p = d / name
    # path-traversal guard: the resolved target must stay inside the asset dir
    if p.resolve().parent != d.resolve():
        return jsonify({"error": "forbidden path"}), 400
    if not p.is_file():
        return jsonify({"error": f"asset not found: {name}"}), 404
    p.unlink()
    return jsonify({"deleted": name})


# ---- audio streaming (preview/download) shared by all pages ----

audio_bp = Blueprint("audio", __name__, url_prefix="/audio")

SERVE_SUBDIRS = ("music", "sfx", "output", "segments")


@audio_bp.get("/<path:sub>")
def serve_audio(sub: str):
    first = sub.replace("\\", "/").split("/")[0]
    if first not in SERVE_SUBDIRS:
        return jsonify({"error": "forbidden path"}), 403
    return send_from_directory(AUDIO, sub)
