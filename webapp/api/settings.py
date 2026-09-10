from __future__ import annotations

import os
import re

from flask import Blueprint, jsonify, request

from ..services.envfile import ENV_PATH, mask, read_env, remove_env, update_env

bp = Blueprint("settings", __name__, url_prefix="/api/settings")

# keys the web UI is allowed to read (masked) / write
SECRET_KEYS = ("MINIMAX_API_KEY", "MINIMAX_GROUP_ID")
PLAIN_KEYS = ("TTS_PROVIDER", "MINIMAX_MODEL", "TTS_SPEED", "MINIMAX_VOICE_ID",
              "PODCAST_NAME", "PODCAST_ARTIST",
              "LOUDNORM_I", "LOUDNORM_TP", "LOUDNORM_LRA")
WRITABLE = set(SECRET_KEYS) | set(PLAIN_KEYS)
# keys that may be wiped back to "unset" (restore code defaults)
CLEARABLE = ("MINIMAX_MODEL", "TTS_SPEED", "MINIMAX_VOICE_ID",
             "PODCAST_NAME", "PODCAST_ARTIST",
             "LOUDNORM_I", "LOUDNORM_TP", "LOUDNORM_LRA")

RANGES = {
    "TTS_SPEED": (0.5, 2.0),
    "LOUDNORM_I": (-35.0, -5.0),
    "LOUDNORM_TP": (-9.0, 0.0),
    "LOUDNORM_LRA": (1.0, 50.0),
}


def _validate(key: str, value: str) -> str | None:
    if key not in WRITABLE:
        return f"unknown setting: {key}"
    if key == "TTS_PROVIDER" and value not in ("dryrun", "minimax"):
        return "TTS_PROVIDER must be dryrun or minimax"
    if key == "MINIMAX_VOICE_ID":
        # system voices like "Chinese (Mandarin)_Radio_Host" contain spaces/parens;
        # only guard against chars that would break the .env key=value format
        if any(c in value for c in ("\n", "\r", "=")):
            return "MINIMAX_VOICE_ID contains illegal characters"
        return None
    if key in RANGES:
        lo, hi = RANGES[key]
        try:
            v = float(value)
        except ValueError:
            return f"{key} must be a number"
        if not lo <= v <= hi:
            return f"{key} must be between {lo} and {hi}"
    if not re.fullmatch(r"[\w\-.,#/+=:@ ]*", value):
        return f"illegal characters in {key}"
    return None


@bp.get("")
def get_settings():
    env = read_env()
    out: dict = {}
    for k in SECRET_KEYS:
        out[k] = {"set": bool(env.get(k)), "masked": mask(env.get(k, ""))}
    for k in PLAIN_KEYS:
        out[k] = env.get(k) or os.environ.get(k, "")
    out["env_file_exists"] = ENV_PATH.exists()
    return jsonify(out)


@bp.post("")
def save_settings():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid payload"}), 400
    updates: dict[str, str] = {}
    clearing: list[str] = []
    errors: list[str] = []
    for key, value in data.items():
        if value is None:
            # explicit null = wipe the key, restoring code defaults
            if key in CLEARABLE:
                clearing.append(key)
            elif key in WRITABLE:
                errors.append(f"{key} cannot be cleared")
            else:
                errors.append(f"unknown setting: {key}")
            continue
        value = str(value).strip()
        if not value:
            continue
        err = _validate(key, value)
        if err:
            errors.append(err)
        else:
            updates[key] = value
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    if not updates and not clearing:
        return jsonify({"error": "nothing to save"}), 400
    if clearing:
        remove_env(clearing)
    if updates:
        update_env(updates)
    return jsonify({"saved": sorted(updates), "cleared": sorted(clearing)}), 200
