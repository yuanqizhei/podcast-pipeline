from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

from pydub import AudioSegment

from .parser import resolve_audio


def loudnorm_target() -> str:
    """Loudness target, overridable via env (LOUDNORM_I/TP/LRA) so the web UI
    can tune it without code changes."""
    i = os.environ.get("LOUDNORM_I", "-16")
    tp = os.environ.get("LOUDNORM_TP", "-1.5")
    lra = os.environ.get("LOUDNORM_LRA", "11")
    return f"I={i}:TP={tp}:LRA={lra}"


def _id3_args(episode: str) -> list[str]:
    """ID3 tags for the final mp3: title = episode name, artist/album from
    env (PODCAST_ARTIST / PODCAST_NAME) when set."""
    args = ["-metadata", f"title={episode}"]
    artist = os.environ.get("PODCAST_ARTIST", "").strip()
    album = os.environ.get("PODCAST_NAME", "").strip()
    if artist:
        args += ["-metadata", f"artist={artist}"]
    if album:
        args += ["-metadata", f"album={album}"]
        args += ["-metadata", f"album_artist={artist or album}"]
    return args


def check_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH; install it first (winget install Gyan.FFmpeg)")
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe not found in PATH; ffmpeg and ffprobe must be installed together")
    return ffmpeg


def _bed_chain(index: int, bed: dict) -> tuple[str, str]:
    start_s = bed["start_ms"] / 1000
    end_s = bed["end_ms"] / 1000
    dur = max(end_s - start_s, 0.5)
    fin = min(bed["fade_in"], dur / 2)
    fout = min(bed["fade_out"], dur / 2)
    parts = [
        f"[{index}:a]aformat=sample_rates=32000:channel_layouts=mono",
        f"atrim=0:{dur:.3f}",
        "asetpts=PTS-STARTPTS",
        f"adelay={int(bed['start_ms'])}:all=1",
        f"volume={bed['gain_db']}dB",
    ]
    if fin > 0.05:
        parts.append(f"afade=t=in:st=0:d={fin:.3f}")
    if fout > 0.05:
        parts.append(f"afade=t=out:st={dur - fout:.3f}:d={fout:.3f}")
    label = f"b{index}"
    return ",".join(parts) + f"[{label}]", label


def _run_ffmpeg(ffmpeg: str, cmd: list[str], on_line=None) -> subprocess.CompletedProcess:
    if on_line is None:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")
        return result
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    stderr_tail: list[str] = []
    try:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_tail.append(line)
            if len(stderr_tail) > 80:
                stderr_tail.pop(0)
            on_line(line)
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{''.join(stderr_tail)[-2000:]}")
    return subprocess.CompletedProcess(cmd, proc.returncode, "", "".join(stderr_tail))


def _measure_loudnorm(ffmpeg: str, base_cmd: list[str], pre_filter: str) -> dict | None:
    probe = base_cmd + [
        "-filter_complex", f"{pre_filter};[mixout]loudnorm={loudnorm_target()}:print_format=json[out]",
        "-map", "[out]", "-f", "null", "-",
    ]
    result = _run_ffmpeg(ffmpeg, probe)
    matches = re.findall(r"\[Parsed_loudnorm_\d+ @ [^\]]*\]\s*(\{[^}]+\})", result.stderr)
    if not matches:
        return None
    try:
        payload = json.loads(matches[-1])
        measured = {
            "measured_I": float(payload["input_i"]),
            "measured_TP": float(payload["input_tp"]),
            "measured_LRA": float(payload["input_lra"]),
            "measured_thresh": float(payload["input_thresh"]),
            "offset": float(payload["target_offset"]),
        }
    except (KeyError, ValueError):
        return None
    if any(not math.isfinite(v) for v in measured.values()):
        return None
    return measured


def mix(voice_path: Path, beds_path: Path, output_path: Path, audio_root: Path, on_event=None) -> Path:
    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    ffmpeg = check_ffmpeg()
    emit({"stage": "mix", "kind": "start"})
    info = json.loads(beds_path.read_text(encoding="utf-8"))
    all_beds = info["beds"]
    total_s = info["total_ms"] / 1000
    beds = []
    for b in all_beds:
        path = resolve_audio(b["file"], audio_root)
        if path.exists():
            beds.append((b, path))
        else:
            msg = f"[warn] bed asset missing, skipped: {b['file']}"
            print(msg)
            emit({"stage": "mix", "kind": "log", "message": msg})

    base_cmd = [ffmpeg, "-y", "-i", str(voice_path)]
    for bed, path in beds:
        base_cmd += ["-stream_loop", "-1", "-i", str(path)]

    chains: list[str] = []
    labels: list[str] = []
    for i, (bed, path) in enumerate(beds, start=1):
        chain, label = _bed_chain(i, bed)
        chains.append(chain)
        labels.append(label)

    final_mix = "[0:a]"
    if labels:
        if len(labels) > 1:
            chains.append("".join(f"[{l}]" for l in labels) + f"amix=inputs={len(labels)}:duration=longest,volume={len(labels)}[bg]")
            bg = "[bg]"
        else:
            bg = f"[{labels[0]}]"
        chains.append(
            f"{bg}[0:a]sidechaincompress=threshold=0.03:ratio=8:attack=50:release=600[ducked]"
        )
        final_mix = "[ducked]"
        chains.append(
            f"{final_mix}[0:a]amix=inputs=2:duration=longest,volume=2.0,"
            "alimiter=limit=0.95[mixout]"
        )
    else:
        chains.append(f"{final_mix}alimiter=limit=0.95[mixout]")
    pre_filter = ";".join(chains)

    target = loudnorm_target()
    print("[ffmpeg pass 1] measuring loudness ...")
    emit({"stage": "mix", "kind": "log", "message": "[ffmpeg pass 1] measuring loudness ..."})
    measured = _measure_loudnorm(ffmpeg, base_cmd, pre_filter)
    if measured:
        params = ":".join(f"{k}={v}" for k, v in measured.items())
        loudnorm = f"loudnorm={target}:{params}:linear=true"
        msg = f"[ffmpeg pass 2] linear loudnorm ({measured['measured_I']} LUFS measured)"
    else:
        loudnorm = f"loudnorm={target}"
        msg = "[ffmpeg pass 2] dynamic loudnorm (measurement unavailable, e.g. silent input)"
    print(msg)
    emit({"stage": "mix", "kind": "log", "message": msg})

    cmd = base_cmd + [
        "-filter_complex", f"{pre_filter};[mixout]{loudnorm}[out]",
        "-map", "[out]",
        "-t", f"{total_s:.3f}",
        "-ar", "44100",
        "-b:a", "128k",
        *_id3_args(output_path.stem.removesuffix("_final")),
        str(output_path),
    ]

    time_re = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")

    def on_ffmpeg_line(line: str) -> None:
        m = time_re.search(line)
        if m:
            t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            emit(
                {
                    "stage": "mix",
                    "kind": "progress",
                    "current": round(t, 3),
                    "total": round(total_s, 3),
                    "percent": min(t / total_s, 1.0) if total_s > 0 else 1.0,
                }
            )

    print("[ffmpeg]", " ".join(cmd))
    emit({"stage": "mix", "kind": "log", "message": "[ffmpeg] " + " ".join(cmd)})
    _run_ffmpeg(ffmpeg, cmd, on_line=on_ffmpeg_line)

    done = AudioSegment.from_file(output_path)
    print(f"final mix: {output_path} ({len(done) / 1000:.1f}s)")
    emit({"stage": "mix", "kind": "done", "output": str(output_path), "duration_ms": len(done)})

    # loudness verification of the finished file (quality closed-loop)
    report = _measure_loudnorm(ffmpeg, [ffmpeg, "-i", str(output_path)], "[0:a]anull[mixout]")
    if report:
        target_i = float(loudnorm_target().split("I=")[1].split(":")[0])
        diff = float(report["measured_I"]) - target_i
        verdict = "OK" if abs(diff) <= 1.0 else f"偏离目标 {diff:+.1f} LU"
        msg = (
            f"[loudness] 成品实测 I={report['measured_I']} LUFS, TP={report['measured_TP']} dBTP "
            f"(目标 I={target_i}) -> {verdict}"
        )
    else:
        msg = "[loudness] 成品响度测量失败（可忽略，不影响输出）"
    print(msg)
    emit({"stage": "mix", "kind": "log", "message": msg})
    return output_path
