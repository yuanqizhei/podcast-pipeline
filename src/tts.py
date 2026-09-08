from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv()

MINIMAX_BASE = "https://api.minimax.chat/v1"
MAX_CHARS_PER_REQUEST = 350


class TTSProvider:
    def synthesize(self, text: str, out_path: Path) -> None:
        raise NotImplementedError


def split_text(text: str, limit: int = MAX_CHARS_PER_REQUEST) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for sentence in text.replace("！", "！\n").replace("？", "？\n").replace("；", "；\n").replace("。", "。\n").split("\n"):
        if not sentence.strip():
            continue
        if len(current) + len(sentence) > limit and current:
            parts.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        parts.append(current)
    return parts


class DryRunProvider(TTSProvider):
    def __init__(self, sample_rate: int = 32000):
        self.sample_rate = sample_rate

    def synthesize(self, text: str, out_path: Path) -> None:
        est_seconds = max(1.0, len(text) / 4.5)
        seg = (
            AudioSegment.silent(duration=int(est_seconds * 1000), frame_rate=self.sample_rate)
            .set_sample_width(2)
            .set_channels(1)
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        seg.export(out_path, format="mp3")


class MiniMaxProvider(TTSProvider):
    def __init__(self):
        self.api_key = os.environ.get("MINIMAX_API_KEY", "")
        self.group_id = os.environ.get("MINIMAX_GROUP_ID", "")
        self.voice_id = os.environ.get("MINIMAX_VOICE_ID", "")
        self.model = os.environ.get("MINIMAX_MODEL", "speech-01-turbo")
        self.speed = float(os.environ.get("TTS_SPEED", "0.95"))
        if not self.api_key or not self.group_id:
            raise RuntimeError("MINIMAX_API_KEY / MINIMAX_GROUP_ID not set in .env")
        if not self.voice_id:
            raise RuntimeError("MINIMAX_VOICE_ID not set; run `python -m src.cli clone <sample>` first")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def clone_voice(self, sample_path: Path) -> str:
        url = f"{MINIMAX_BASE}/voice_clone?GroupId={self.group_id}"
        with open(sample_path, "rb") as f:
            files = {"file": (sample_path.name, f, "audio/wav")}
            data = {"model_type": "1", "need_volume_control": "false"}
            resp = requests.post(url, headers={"Authorization": f"Bearer {self.api_key}"}, files=files, data=data, timeout=300)
        resp.raise_for_status()
        payload = resp.json()
        voice_id = (
            payload.get("data", {}).get("voice_id")
            or payload.get("data", {}).get("file_id")
            or payload.get("voice_id")
        )
        if not voice_id:
            raise RuntimeError(f"voice clone failed: {json.dumps(payload, ensure_ascii=False)}")
        return voice_id

    def _t2a(self, text: str) -> bytes:
        url = f"{MINIMAX_BASE}/t2a_v2?GroupId={self.group_id}"
        body = {
            "model": self.model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": self.voice_id,
                "speed": self.speed,
                "vol": 1.0,
                "pitch": 0.0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }
        last_err = "unknown error"
        for attempt in range(3):
            try:
                resp = requests.post(url, headers=self._headers(), json=body, timeout=120)
            except requests.exceptions.RequestException as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(3 * (attempt + 1))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code}"
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            payload = resp.json()
            audio_field = payload.get("data", {}).get("audio", "")
            if not audio_field:
                raise RuntimeError(f"t2a empty audio: {json.dumps(payload, ensure_ascii=False)[:500]}")
            try:
                return bytes.fromhex(audio_field)
            except ValueError:
                return base64.b64decode(audio_field)
        raise RuntimeError(f"t2a failed after 3 retries: {last_err}")

    def synthesize(self, text: str, out_path: Path) -> None:
        chunks = split_text(text)
        segments: list[AudioSegment] = []
        for chunk in chunks:
            raw = self._t2a(chunk)
            tmp = out_path.with_suffix(f".part{len(segments)}.mp3")
            tmp.write_bytes(raw)
            segments.append(AudioSegment.from_file(tmp))
            tmp.unlink(missing_ok=True)
        merged = segments[0]
        for seg in segments[1:]:
            merged = merged.append(seg, crossfade=15)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        merged.export(out_path, format="mp3")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def synthesize_timeline(timeline, segments_root: Path, provider: TTSProvider, force: bool = False, on_event=None) -> list[Path]:
    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    segments_dir = segments_root / timeline.episode
    meta_path = segments_dir / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        print(f"[warn] meta.json unreadable, resetting cache index: {meta_path}")
        emit({"stage": "tts", "kind": "log", "message": "[warn] meta.json unreadable, resetting cache index"})
        meta = {}
    speech_items = [i for i in timeline.items if i.type == "speech"]
    total = len(speech_items)
    emit({"stage": "tts", "kind": "start", "total": total})
    produced: list[Path] = []
    for idx, item in enumerate(speech_items, start=1):
        out_path = segments_dir / f"{item.id}.mp3"
        h = text_hash(item.text)
        cached = not force and out_path.exists() and meta.get(item.id) == h
        emit(
            {
                "stage": "tts",
                "kind": "progress",
                "current": idx,
                "total": total,
                "id": item.id,
                "cached": cached,
            }
        )
        if cached:
            produced.append(out_path)
            continue
        provider.synthesize(item.text, out_path)
        meta[item.id] = h
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        produced.append(out_path)
    emit({"stage": "tts", "kind": "done", "total": total})
    return produced


def get_provider(name: str) -> TTSProvider:
    if name == "dryrun":
        return DryRunProvider()
    if name == "minimax":
        return MiniMaxProvider()
    raise ValueError(f"unknown provider: {name}")
