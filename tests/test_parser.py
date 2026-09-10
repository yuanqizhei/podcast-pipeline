"""Unit tests for src/parser.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.parser import clean_ref, hash_script, load_timeline, parse, resolve_audio, text_hash, write_timeline


def test_clean_ref_normalizes_backslashes():
    assert clean_ref("music\\bgm.mp3") == "music/bgm.mp3"


def test_resolve_audio_relative_vs_absolute():
    root = Path("audio")
    assert resolve_audio("music/bgm.mp3", root) == Path("audio/music/bgm.mp3")
    assert resolve_audio("D:/x/y.mp3", root) == Path("D:/x/y.mp3")
    assert resolve_audio("D:\\x\\y.mp3", root) == Path("D:\\x\\y.mp3")


def _write(tmp_path: Path, content: str, name: str = "ep.txt") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_basic_directives(tmp_path):
    p = _write(tmp_path, "hello\nworld\n@pause 2\n@insert sfx/a.mp3 gain=-6\n@bed music/b.mp3\nmore\n@bed_stop\n")
    tl = parse(p)
    kinds = [i.type for i in tl.items]
    assert kinds == ["speech", "pause", "insert", "bed", "speech", "bed_stop"]
    speech = tl.items[0]
    assert speech.text == "hello\nworld"
    assert speech.id == f"s{text_hash(speech.text)}"  # content-addressed id
    ins = tl.items[2]
    assert ins.file == "sfx/a.mp3" and ins.gain_db == -6.0  # relative, portable ref


def test_parse_bom_tolerated(tmp_path):
    p = tmp_path / "bom.txt"
    p.write_bytes(b"\xef\xbb\xbf@pause 1\nhi\n")
    tl = parse(p)
    assert tl.items[0].type == "pause"


def test_parse_unknown_directive_has_lineno(tmp_path):
    p = _write(tmp_path, "ok line\n@nonsense x\n")
    with pytest.raises(ValueError, match="line 2"):
        parse(p)


def test_parse_insert_requires_path(tmp_path):
    p = _write(tmp_path, "@insert gain=-3\n")
    with pytest.raises(ValueError, match="requires a file path"):
        parse(p)


def test_timeline_roundtrip_and_hash(tmp_path):
    p = _write(tmp_path, "a\n@pause 1\nb\n")
    tl = parse(p)
    out = tmp_path / "tl.json"
    write_timeline(tl, out)
    tl2 = load_timeline(out)
    assert tl2.script_hash == tl.script_hash == hash_script(p)
    assert [(i.type, getattr(i, "id", None)) for i in tl.items] == [
        (i.type, getattr(i, "id", None)) for i in tl2.items
    ]
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["items"] and data["script_hash"]
