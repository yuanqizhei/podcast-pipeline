from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

from flask import Blueprint, jsonify, request

from src.parser import parse

from ..services.runner import AUDIO, OUTPUT, SCRIPTS, SEGMENTS

bp = Blueprint("scripts", __name__, url_prefix="/api/scripts")

NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_NAME_ERROR = "script name may only contain letters, digits, '-' and '_'"


def _script_path(name: str) -> Path:
    if not NAME_RE.match(name):
        raise ValueError(SAFE_NAME_ERROR)
    return SCRIPTS / f"{name}.txt"


def _timeline_dict(script_path: Path) -> dict:
    tl = parse(script_path, AUDIO)
    items = []
    missing = []
    for item in tl.items:
        d = asdict(item)
        if item.type in ("insert", "bed"):
            exists = Path(item.file).exists()
            d["exists"] = exists
            d["file"] = str(Path(item.file).relative_to(AUDIO)).replace("\\", "/")
            if not exists:
                missing.append(d["file"])
        items.append(d)
    return {
        "episode": tl.episode,
        "items": items,
        "speech_blocks": sum(1 for i in tl.items if i.type == "speech"),
        "chars": sum(len(i.text) for i in tl.items if i.type == "speech"),
        "missing_assets": missing,
    }


@bp.get("")
def list_scripts():
    SCRIPTS.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(SCRIPTS.glob("*.txt")):
        try:
            tl = _timeline_dict(p)
            seg_dir = SEGMENTS / p.stem
            seg_count = len(list(seg_dir.glob("s*.mp3"))) if seg_dir.exists() else 0
            final = OUTPUT / f"{p.stem}_final.mp3"
            out.append(
                {
                    "name": p.stem,
                    "size": p.stat().st_size,
                    "mtime": p.stat().st_mtime,
                    "speech_blocks": tl["speech_blocks"],
                    "chars": tl["chars"],
                    "missing_assets": tl["missing_assets"],
                    "segment_count": seg_count,
                    "has_final": final.exists(),
                }
            )
        except ValueError as e:
            out.append({"name": p.stem, "parse_error": str(e), "mtime": p.stat().st_mtime})
    return jsonify(out)


@bp.post("")
def create_script():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    content = data.get("content", "")
    path = _script_path(name)
    if path.exists():
        return jsonify({"error": f"script already exists: {name}"}), 400
    SCRIPTS.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return jsonify({"name": name, "created": True}), 201


@bp.get("/<name>")
def get_script(name: str):
    path = _script_path(name)
    if not path.exists():
        return jsonify({"error": f"script not found: {name}"}), 404
    result = {"name": name, "content": path.read_text(encoding="utf-8-sig")}
    try:
        result["timeline"] = _timeline_dict(path)
    except ValueError as e:
        result["timeline"] = None
        result["parse_error"] = str(e)
    return jsonify(result)


@bp.put("/<name>")
def update_script(name: str):
    path = _script_path(name)
    if not path.exists():
        return jsonify({"error": f"script not found: {name}"}), 404
    data = request.get_json(force=True)
    content = data.get("content")
    if content is None:
        return jsonify({"error": "missing 'content'"}), 400
    path.write_text(content, encoding="utf-8")
    result = {"name": name, "saved": True}
    try:
        result["timeline"] = _timeline_dict(path)
    except ValueError as e:
        result["timeline"] = None
        result["parse_error"] = str(e)
    return jsonify(result)


@bp.delete("/<name>")
def delete_script(name: str):
    path = _script_path(name)
    if not path.exists():
        return jsonify({"error": f"script not found: {name}"}), 404
    deleted = {"script": False, "segments": False}
    path.unlink()
    deleted["script"] = True
    if request.args.get("with_segments") == "1":
        seg_dir = SEGMENTS / name
        if seg_dir.exists():
            import shutil

            shutil.rmtree(seg_dir)
            deleted["segments"] = True
    return jsonify({"name": name, "deleted": deleted})


@bp.post("/<name>/parse")
def parse_script(name: str):
    path = _script_path(name)
    if not path.exists():
        return jsonify({"error": f"script not found: {name}"}), 404
    try:
        return jsonify(_timeline_dict(path))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
