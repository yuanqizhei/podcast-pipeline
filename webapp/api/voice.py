from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Blueprint, jsonify, request

from src.tts import MiniMaxProvider

from ..services.envfile import ENV_PATH, update_env
from ..services.runner import ROOT

bp = Blueprint("voice", __name__, url_prefix="/api/voice")

SAMPLE_EXT_OK = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".mp4"}


def _reload_env() -> None:
    load_dotenv(ENV_PATH, override=True)


def _env_status() -> dict:
    return {
        "provider_default": os.environ.get("TTS_PROVIDER", "dryrun"),
        "model": os.environ.get("MINIMAX_MODEL", "speech-01-turbo"),
        "speed": os.environ.get("TTS_SPEED", "0.95"),
        "api_key_set": bool(os.environ.get("MINIMAX_API_KEY")),
        "group_id_set": bool(os.environ.get("MINIMAX_GROUP_ID")),
        "voice_id": os.environ.get("MINIMAX_VOICE_ID") or "",
        "env_file_exists": ENV_PATH.exists(),
    }


@bp.get("")
def voice_status():
    _reload_env()
    return jsonify(_env_status())


@bp.post("/clone")
def clone_voice():
    _reload_env()
    if not os.environ.get("MINIMAX_API_KEY") or not os.environ.get("MINIMAX_GROUP_ID"):
        return jsonify({"error": "MINIMAX_API_KEY / MINIMAX_GROUP_ID not set in .env"}), 400
    if "file" not in request.files:
        return jsonify({"error": "no file part in request"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "empty filename"}), 400
    suffix = Path(f.filename).suffix.lower()
    if suffix not in SAMPLE_EXT_OK:
        return jsonify({"error": f"sample must be one of {sorted(SAMPLE_EXT_OK)}"}), 400

    tmp_dir = ROOT / "audio" / "output" / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"clone_sample{suffix}"
    f.save(tmp)
    try:
        # normalize any input format (incl. browser webm/opus recordings) to
        # wav before sending to MiniMax
        from pydub import AudioSegment

        wav = tmp.with_suffix(".wav")
        AudioSegment.from_file(tmp).export(wav, format="wav")
        prov = MiniMaxProvider.__new__(MiniMaxProvider)
        prov.api_key = os.environ["MINIMAX_API_KEY"]
        prov.group_id = os.environ["MINIMAX_GROUP_ID"]
        try:
            voice_id = prov.clone_voice(wav)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": f"clone failed: {e}"}), 502
        finally:
            wav.unlink(missing_ok=True)
    finally:
        tmp.unlink(missing_ok=True)

    import re as _re

    if not _re.fullmatch(r"[\w\-]+", voice_id):
        return jsonify({"error": f"clone returned invalid voice_id: {voice_id!r}"}), 502

    update_env({"MINIMAX_VOICE_ID": voice_id})
    return jsonify({"voice_id": voice_id, "saved": True})


@bp.post("/speed")
def set_speed():
    data = request.get_json(force=True)
    try:
        speed = float(data.get("speed"))
        if not 0.5 <= speed <= 2.0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "speed must be a number between 0.5 and 2.0"}), 400
    update_env({"TTS_SPEED": str(speed)})
    return jsonify({"speed": speed, "saved": True})
