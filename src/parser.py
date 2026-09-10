from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

DIRECTIVE_RE = re.compile(r"^@(\w+)\s*(.*)$")
KV_RE = re.compile(r"([a-z_]+)=([-\w.]+)")
WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def clean_ref(path: str) -> str:
    """Normalize a script path reference to forward slashes so the timeline
    JSON stays identical across platforms."""
    return Path(path.replace("\\", "/")).as_posix()


def resolve_audio(ref: str, audio_root: Path) -> Path:
    """Resolve a file reference from the timeline / beds.json against the
    audio root. Relative refs are portable across machines; absolute refs
    (including Windows drive paths from old timelines) are used as-is."""
    if Path(ref).is_absolute() or WIN_DRIVE_RE.match(ref):
        return Path(ref)
    return audio_root / ref


@dataclass
class Speech:
    type: str = "speech"
    id: str = ""
    text: str = ""


@dataclass
class Pause:
    type: str = "pause"
    seconds: float = 1.0


@dataclass
class Insert:
    type: str = "insert"
    file: str = ""
    gain_db: float = 0.0
    fade_in: float = 0.5
    fade_out: float = 0.5


@dataclass
class Bed:
    type: str = "bed"
    file: str = ""
    gain_db: float = -20.0
    fade_in: float = 3.0
    fade_out: float = 3.0


@dataclass
class BedStop:
    type: str = "bed_stop"


@dataclass
class Timeline:
    episode: str = ""
    script_hash: str = ""
    items: list = field(default_factory=list)


def parse_kv(payload: str) -> dict:
    return {k: v for k, v in KV_RE.findall(payload)}


def hash_script(script_path: Path) -> str:
    return hashlib.sha256(script_path.read_bytes()).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def parse(script_path: Path) -> Timeline:
    episode = script_path.stem
    items: list = []
    speech_lines: list[str] = []

    def flush_speech():
        nonlocal speech_lines
        if not speech_lines:
            return
        text = "\n".join(speech_lines).strip()
        # content-based id: inserting/deleting blocks elsewhere in the script
        # must not shift ids (and thus invalidate the TTS cache)
        items.append(Speech(id=f"s{text_hash(text)}", text=text))
        speech_lines = []

    for lineno, raw in enumerate(script_path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw.strip()
        if not line:
            flush_speech()
            continue
        if line.startswith("#"):
            continue
        m = DIRECTIVE_RE.match(line)
        if not m:
            speech_lines.append(line)
            continue

        cmd, payload = m.group(1), m.group(2).strip()
        if cmd == "pause":
            flush_speech()
            token = payload.split()[0] if payload.split() else ""
            try:
                seconds = float(token)
            except ValueError:
                print(f"[warn] line {lineno}: bad @pause value '{payload}', expected seconds like '@pause 2' -> using 1.0s")
                seconds = 1.0
            items.append(Pause(seconds=seconds))
        elif cmd in ("insert", "bed"):
            flush_speech()
            tokens = payload.split()
            if not tokens or "=" in tokens[0]:
                raise ValueError(f"line {lineno}: @{cmd} requires a file path (e.g. '@{cmd} music/bgm.mp3 gain=-20')")
            try:
                kv = parse_kv(payload)
                params = dict(
                    file=clean_ref(tokens[0]),
                    gain_db=float(kv.get("gain", 0 if cmd == "insert" else -20)),
                    fade_in=float(kv.get("fade_in", 0.5 if cmd == "insert" else 3)),
                    fade_out=float(kv.get("fade_out", 0.5 if cmd == "insert" else 3)),
                )
            except ValueError as e:
                raise ValueError(f"line {lineno}: bad @{cmd} parameters '{payload}': {e}") from e
            items.append(Insert(**params) if cmd == "insert" else Bed(**params))
        elif cmd == "bed_stop":
            flush_speech()
            items.append(BedStop())
        else:
            raise ValueError(f"line {lineno}: unknown directive @{cmd} in {script_path.name}")

    flush_speech()
    return Timeline(episode=episode, script_hash=hash_script(script_path), items=items)


def write_timeline(timeline: Timeline, out_path: Path) -> None:
    data = {
        "episode": timeline.episode,
        "script_hash": timeline.script_hash,
        "items": [asdict(i) for i in timeline.items],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_timeline(json_path: Path) -> Timeline:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    items = []
    for it in data["items"]:
        kind = it.pop("type")
        if kind == "speech":
            items.append(Speech(**it))
        elif kind == "pause":
            items.append(Pause(**it))
        elif kind == "insert":
            items.append(Insert(**it))
        elif kind == "bed":
            items.append(Bed(**it))
        elif kind == "bed_stop":
            items.append(BedStop())
    return Timeline(episode=data["episode"], script_hash=data.get("script_hash", ""), items=items)
