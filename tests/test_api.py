"""Integration tests for the Web API (Flask test client, isolated tmp workspace)."""
from __future__ import annotations

import io
import json
import time
import wave

from src.parser import parse, text_hash


def _wav_bytes(seconds: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


# ---------- scripts ----------

def test_script_crud_and_parse(client):
    r = client.post("/api/scripts", json={"name": "ep1", "content": "hello\n@pause 1\nworld"})
    assert r.status_code == 201
    r = client.get("/api/scripts/ep1")
    assert r.status_code == 200 and r.get_json()["timeline"]["speech_blocks"] == 2
    r = client.post("/api/scripts/ep1/parse")
    assert r.status_code == 200
    r = client.delete("/api/scripts/ep1")
    assert r.status_code == 200


def test_script_bad_name_400_not_500(client):
    r = client.get("/api/scripts/bad!name")
    assert r.status_code == 400 and "error" in r.get_json()


def test_script_rename_moves_segments(client, tmp_project):
    client.post("/api/scripts", json={"name": "old", "content": "hi"})
    seg_dir = tmp_project / "audio" / "segments" / "old"
    seg_dir.mkdir(parents=True)
    r = client.post("/api/scripts/old/rename", json={"new_name": "new"})
    assert r.status_code == 200
    assert (tmp_project / "audio" / "segments" / "new").exists()
    assert not seg_dir.exists()
    assert not (tmp_project / "script" / "old.txt").exists()


def test_script_rename_conflicts(client):
    client.post("/api/scripts", json={"name": "a", "content": "x"})
    client.post("/api/scripts", json={"name": "b", "content": "x"})
    assert client.post("/api/scripts/a/rename", json={"new_name": "b"}).status_code == 400
    assert client.post("/api/scripts/a/rename", json={"new_name": "bad!"}).status_code == 400


# ---------- settings ----------

def test_settings_write_read_clear(client, tmp_project):
    assert client.post("/api/settings", json={"TTS_SPEED": "1.2"}).status_code == 200
    env = (tmp_project / ".env").read_text(encoding="utf-8")
    assert "TTS_SPEED=1.2" in env
    r = client.post("/api/settings", json={"TTS_SPEED": None})  # restore default
    assert r.status_code == 200
    assert "TTS_SPEED" not in (tmp_project / ".env").read_text(encoding="utf-8")


def test_settings_validation(client):
    assert client.post("/api/settings", json={"TTS_SPEED": "9"}).status_code == 400
    assert client.post("/api/settings", json={"LOUDNORM_TP": "5"}).status_code == 400
    assert client.post("/api/settings", json={"PODCAST_NAME": "a\nEVIL=1"}).status_code == 400
    assert client.post("/api/settings", json={"MINIMAX_API_KEY": None}).status_code == 400  # secrets not clearable


def test_settings_secret_masked(client, tmp_project):
    (tmp_project / ".env").write_text("MINIMAX_API_KEY=sk-abcdef1234567890\n", encoding="utf-8")
    data = client.get("/api/settings").get_json()
    assert data["MINIMAX_API_KEY"]["set"] is True
    assert "abcdef" not in data["MINIMAX_API_KEY"]["masked"]


# ---------- assets ----------

def test_asset_upload_list_delete(client, tmp_project):
    r = client.post("/api/assets/sfx", data={"file": (io.BytesIO(_wav_bytes()), "t.wav", "audio/wav")},
                    content_type="multipart/form-data")
    assert r.status_code == 201
    listed = client.get("/api/assets/sfx").get_json()
    assert any(a["name"] == "t.wav" and a["duration"] for a in listed)
    assert client.get("/audio/sfx/t.wav").status_code == 200
    assert client.delete("/api/assets/sfx/t.wav").status_code == 200


def test_asset_guards(client):
    assert client.post("/api/assets/sfx", data={"file": (io.BytesIO(b"MZ"), "x.exe", "application/octet-stream")},
                       content_type="multipart/form-data").status_code == 400
    assert client.post("/api/assets/sfx", data={"file": (io.BytesIO(b"x"), "CON.wav", "audio/wav")},
                       content_type="multipart/form-data").status_code == 400
    # raw traversal-style path (not normalized by the client)
    assert client.delete("/api/assets/sfx/../../.env").status_code in (400, 404)


# ---------- jobs ----------

def test_job_submit_validates_script(client):
    assert client.post("/api/jobs", json={"script": "ghost", "command": "build"}).status_code == 400
    assert client.post("/api/jobs", json={"script": "x", "command": "nope"}).status_code == 400


def test_job_dryrun_build_end_to_end(client, tmp_project):
    (tmp_project / "script" / "ep.txt").write_text("hello\n@pause 1\nworld\n", encoding="utf-8")
    r = client.post("/api/jobs", json={"script": "ep", "command": "build", "provider": "dryrun", "limit": 2})
    assert r.status_code == 201
    jid = r.get_json()["job"]["id"]
    for _ in range(30):
        j = client.get(f"/api/jobs/{jid}").get_json()
        if j["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.5)
    assert j["status"] == "done", j.get("error")
    out = tmp_project / "audio" / "output"
    assert (out / "ep_final.mp3").exists()
    ch = json.loads((out / "ep_chapters.json").read_text(encoding="utf-8"))
    assert len(ch["chapters"]) == 2
    # history persisted
    assert any(json.loads(l)["id"] == jid for l in
               (tmp_project / "data" / "jobs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())


def test_segments_prune_rescues_legacy(client, tmp_project):
    script = tmp_project / "script" / "ep.txt"
    script.write_text("hello\n@pause 1\nworld\n", encoding="utf-8")
    seg = tmp_project / "audio" / "segments" / "ep"
    seg.mkdir(parents=True)
    tl = parse(script)
    speeches = [i for i in tl.items if i.type == "speech"]
    # legacy positional cache for speech #2 (id not in live set, but meta hash matches)
    legacy = seg / "s001.mp3"
    legacy.write_bytes(b"paid-audio")
    meta = {"s001": text_hash(speeches[1].text), "deadbeef": "x"}
    (seg / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    # orphan with no meta entry
    (seg / "s_deadbeef.mp3").write_bytes(b"junk")
    r = client.post("/api/episodes/ep/segments/prune")
    assert r.status_code == 200
    body = r.get_json()
    assert body["removed"] == 1 and body["ids"] == ["s_deadbeef"]
    assert (seg / f"{speeches[1].id}.mp3").exists()  # rescued by rename
    assert not legacy.exists()
