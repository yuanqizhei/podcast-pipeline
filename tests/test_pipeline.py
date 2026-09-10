"""Unit tests for the dryrun pipeline: tts cache, assemble chapters, mix guards."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.assemble import assemble
from src.mix import loudnorm_target, mix
from src.parser import parse
from src.tts import DryRunProvider, synthesize_timeline


@pytest.fixture
def script(tmp_path: Path) -> Path:
    p = tmp_path / "script" / "ep.txt"
    p.parent.mkdir(exist_ok=True)
    p.write_text("first block\n@pause 1\nsecond block\n", encoding="utf-8")
    return p


def _timeline(script: Path, n_speech: int | None = None):
    tl = parse(script)
    if n_speech is not None:
        seen = 0
        items = []
        for it in tl.items:
            if it.type == "speech":
                seen += 1
                if seen > n_speech:
                    break
            items.append(it)
        tl.items = items
    return tl


def test_dryrun_synthesize_and_cache_hit(script, tmp_path):
    seg_root = tmp_path / "audio" / "segments"
    tl = _timeline(script)
    n1 = synthesize_timeline(tl, seg_root, DryRunProvider())
    assert len(n1) == 2 and all(p.exists() for p in n1)
    meta = json.loads((seg_root / tl.episode / "meta.json").read_text(encoding="utf-8"))
    assert len(meta) == 2
    # second run: everything cached, mtimes unchanged
    before = {p.stem: p.stat().st_mtime_ns for p in n1}
    n2 = synthesize_timeline(tl, seg_root, DryRunProvider())
    after = {p.stem: p.stat().st_mtime_ns for p in n2}
    assert before == after


def test_force_resynthesizes(script, tmp_path):
    seg_root = tmp_path / "audio" / "segments"
    tl = _timeline(script)
    synthesize_timeline(tl, seg_root, DryRunProvider())
    first = sorted((seg_root / tl.episode).glob("*.mp3"))[0].stat().st_mtime_ns
    synthesize_timeline(tl, seg_root, DryRunProvider(), force=True)
    second = sorted((seg_root / tl.episode).glob("*.mp3"))[0].stat().st_mtime_ns
    assert second >= first


def test_assemble_episode_isolation_and_chapters(script, tmp_path):
    audio = tmp_path / "audio"
    tl = _timeline(script)
    synthesize_timeline(tl, audio / "segments", DryRunProvider())
    # limit preview: assemble only 1 speech block
    tl1 = _timeline(script, n_speech=1)
    voice, beds = assemble(tl1, audio / "segments", audio / "output", audio)
    info = json.loads(beds.read_text(encoding="utf-8"))
    assert info["episode"] == "ep"
    ch_path = audio / "output" / "ep_chapters.json"
    ch = json.loads(ch_path.read_text(encoding="utf-8"))
    assert len(ch["chapters"]) == 1
    assert ch["chapters"][0]["start"] == 0.0 and ch["chapters"][0]["end"] > 0
    assert ch["total_ms"] == info["total_ms"]


def test_mix_empty_track_clear_error(tmp_path):
    audio = tmp_path / "audio"
    (audio / "output").mkdir(parents=True)
    voice = audio / "output" / "voice_track.wav"
    beds = audio / "output" / "beds.json"
    voice.write_bytes(b"x")  # content irrelevant; guard fires before ffmpeg
    beds.write_text(json.dumps({"episode": "ep", "total_ms": 0, "beds": []}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="voice track is empty"):
        mix(voice, beds, audio / "out.mp3", audio)


def test_loudnorm_target_env_override(monkeypatch):
    monkeypatch.delenv("LOUDNORM_I", raising=False)
    monkeypatch.delenv("LOUDNORM_TP", raising=False)
    monkeypatch.delenv("LOUDNORM_LRA", raising=False)
    assert loudnorm_target() == "I=-16:TP=-1.5:LRA=11"
    monkeypatch.setenv("LOUDNORM_I", "-14")
    assert "I=-14" in loudnorm_target()
