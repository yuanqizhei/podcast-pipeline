from __future__ import annotations

import json
from pathlib import Path

from pydub import AudioSegment

from .parser import resolve_audio

SAMPLE_RATE = 32000


def _load(path: Path, gain_db: float, fade_in: float, fade_out: float) -> AudioSegment:
    if not path.exists():
        raise FileNotFoundError(f"audio asset missing: {path}")
    seg = AudioSegment.from_file(path).set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
    seg = seg.apply_gain(gain_db)
    if fade_in > 0:
        seg = seg.fade_in(int(fade_in * 1000))
    if fade_out > 0:
        seg = seg.fade_out(int(fade_out * 1000))
    return seg


def assemble(timeline, segments_root: Path, output_dir: Path, audio_root: Path, on_event=None) -> tuple[Path, Path]:
    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    segments_dir = segments_root / timeline.episode
    voice_path = output_dir / "voice_track.wav"
    beds_path = output_dir / "beds.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    emit({"stage": "assemble", "kind": "start"})

    main = AudioSegment.silent(duration=0, frame_rate=SAMPLE_RATE).set_sample_width(2).set_channels(1)
    beds: list[dict] = []
    open_bed = None
    missing: list[str] = []

    for item in timeline.items:
        if item.type == "speech":
            seg_path = segments_dir / f"{item.id}.mp3"
            if not seg_path.exists():
                missing.append(str(seg_path))
                continue
            main += AudioSegment.from_file(seg_path).set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
        elif item.type == "pause":
            main += AudioSegment.silent(duration=int(item.seconds * 1000), frame_rate=SAMPLE_RATE).set_sample_width(2).set_channels(1)
        elif item.type == "insert":
            try:
                main += _load(resolve_audio(item.file, audio_root), item.gain_db, item.fade_in, item.fade_out)
            except FileNotFoundError as e:
                missing.append(str(e))
        elif item.type == "bed":
            if open_bed is not None:
                open_bed["end_ms"] = len(main)
                beds.append(open_bed)
                open_bed = None
            open_bed = {
                "file": item.file,
                "gain_db": item.gain_db,
                "fade_in": item.fade_in,
                "fade_out": item.fade_out,
                "start_ms": len(main),
                "end_ms": None,
            }
        elif item.type == "bed_stop":
            if open_bed is not None:
                open_bed["end_ms"] = len(main)
                beds.append(open_bed)
                open_bed = None

    if open_bed is not None:
        open_bed["end_ms"] = len(main) + int(open_bed["fade_out"] * 1000)
        beds.append(open_bed)

    main.export(voice_path, format="wav")
    beds_path.write_text(
        json.dumps({"episode": timeline.episode, "total_ms": len(main), "beds": beds}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if missing:
        msg = "[warn] skipped missing assets: " + ", ".join(missing)
        print(msg)
        emit({"stage": "assemble", "kind": "log", "message": msg})
    print(f"voice track: {voice_path} ({len(main) / 1000:.1f}s), beds: {len(beds)}")
    emit({"stage": "assemble", "kind": "done", "total_ms": len(main), "beds": len(beds), "missing": len(missing)})
    return voice_path, beds_path
