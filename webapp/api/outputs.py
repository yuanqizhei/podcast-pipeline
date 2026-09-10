from __future__ import annotations

import json
import shutil
from pathlib import Path

from flask import Blueprint, jsonify

from ..services.runner import OUTPUT, ROOT, SCRIPTS, SEGMENTS, preflight
from src.parser import parse
from src.tts import _migrate_legacy_cache

bp = Blueprint("outputs", __name__, url_prefix="/api")

_ffmpeg_checked: dict = {}


def _ffmpeg_status() -> dict:
    if not _ffmpeg_checked:
        _ffmpeg_checked["ffmpeg"] = bool(shutil.which("ffmpeg"))
        _ffmpeg_checked["ffprobe"] = bool(shutil.which("ffprobe"))
    return _ffmpeg_checked


@bp.get("/env")
def env_info():
    return jsonify(
        {
            "ffmpeg": _ffmpeg_status(),
            "minimax_preflight_errors": preflight("minimax"),
        }
    )


@bp.get("/outputs")
def list_outputs():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    episodes = {p.stem for p in SCRIPTS.glob("*.txt")} if SCRIPTS.exists() else set()
    finals = []
    intermediates = []
    for p in sorted(OUTPUT.iterdir(), key=lambda x: -x.stat().st_mtime):
        if not p.is_file():
            continue
        entry = {"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime}
        if p.name.endswith("_final.mp3"):
            entry["episode"] = p.name[: -len("_final.mp3")]
            finals.append(entry)
        elif p.name == "voice_track.wav":
            entry["kind"] = "voice_track"
            intermediates.append(entry)
        elif p.name == "beds.json":
            entry["kind"] = "beds"
            intermediates.append(entry)
        elif p.name.endswith("_chapters.json") and p.stem[: -len("_chapters")] in episodes:
            entry["kind"] = "chapters"
            entry["episode"] = p.stem[: -len("_chapters")]
            intermediates.append(entry)
        elif p.name.endswith("_timeline.json") and p.stem[: -len("_timeline")] in episodes:
            entry["kind"] = "timeline"
            entry["episode"] = p.stem[: -len("_timeline")]
            intermediates.append(entry)
    return jsonify({"finals": finals, "intermediates": intermediates})


@bp.get("/episodes/<name>/segments")
def list_segments(name: str):
    seg_dir = SEGMENTS / name
    if not seg_dir.exists():
        return jsonify([])
    meta_path = seg_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}
    out = []
    for p in sorted(seg_dir.glob("s*.mp3")):
        out.append(
            {
                "id": p.stem,
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
                "hash": meta.get(p.stem, ""),
            }
        )
    return jsonify(out)


@bp.delete("/episodes/<name>/segments")
def clear_segments(name: str):
    seg_dir = SEGMENTS / name
    if not seg_dir.exists():
        return jsonify({"error": "no cache for this episode"}), 404
    shutil.rmtree(seg_dir)
    return jsonify({"cleared": name})


@bp.delete("/episodes/<name>/segments/<seg_id>")
def delete_segment(name: str, seg_id: str):
    seg_dir = SEGMENTS / name
    p = seg_dir / f"{seg_id}.mp3"
    meta_path = seg_dir / "meta.json"
    if not p.exists():
        return jsonify({"error": f"segment not found: {seg_id}"}), 404
    p.unlink()
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta.pop(seg_id, None)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass
    return jsonify({"deleted": seg_id})


@bp.post("/episodes/<name>/segments/prune")
def prune_segments(name: str):
    """Remove cached segments whose ids no longer appear in the current script
    (leftovers from script edits)."""
    seg_dir = SEGMENTS / name
    script_path = SCRIPTS / f"{name}.txt"
    if not seg_dir.exists():
        return jsonify({"error": f"no cache for this episode"}), 404
    if not script_path.exists():
        return jsonify({"error": f"script not found: {name}"}), 400
    try:
        tl = parse(script_path)
    except ValueError as e:
        return jsonify({"error": f"script parse failed: {e}"}), 400
    live_ids = {i.id for i in tl.items if i.type == "speech"}
    meta_path = seg_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}
    # rescue legacy positional-id caches (possibly paid audio) first: they are
    # renamed to content ids instead of being deleted as orphans
    speech_items = [i for i in tl.items if i.type == "speech"]
    _migrate_legacy_cache(speech_items, seg_dir, meta, meta_path)
    removed = []
    for p in seg_dir.glob("*.mp3"):
        if p.stem not in live_ids:
            p.unlink()
            meta.pop(p.stem, None)
            removed.append(p.stem)
    if removed:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"removed": len(removed), "ids": removed})
