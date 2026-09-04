from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from pydub import AudioSegment

LOUDNORM_TARGET = "I=-16:TP=-1.5:LRA=11"


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


def _run_ffmpeg(ffmpeg: str, cmd: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")
    return result


def _measure_loudnorm(ffmpeg: str, base_cmd: list[str], pre_filter: str) -> dict | None:
    probe = base_cmd + [
        "-filter_complex", f"{pre_filter};[mixout]loudnorm={LOUDNORM_TARGET}:print_format=json[out]",
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


def mix(voice_path: Path, beds_path: Path, output_path: Path) -> Path:
    ffmpeg = check_ffmpeg()
    info = json.loads(beds_path.read_text(encoding="utf-8"))
    all_beds = info["beds"]
    total_s = info["total_ms"] / 1000
    beds = [b for b in all_beds if Path(b["file"]).exists()]
    for b in all_beds:
        if b not in beds:
            print(f"[warn] bed asset missing, skipped: {b['file']}")

    base_cmd = [ffmpeg, "-y", "-i", str(voice_path)]
    for bed in beds:
        base_cmd += ["-stream_loop", "-1", "-i", str(bed["file"])]

    chains: list[str] = []
    labels: list[str] = []
    for i, bed in enumerate(beds, start=1):
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

    print("[ffmpeg pass 1] measuring loudness ...")
    measured = _measure_loudnorm(ffmpeg, base_cmd, pre_filter)
    if measured:
        params = ":".join(f"{k}={v}" for k, v in measured.items())
        loudnorm = f"loudnorm={LOUDNORM_TARGET}:{params}:linear=true"
        print(f"[ffmpeg pass 2] linear loudnorm ({measured['measured_I']} LUFS measured)")
    else:
        loudnorm = f"loudnorm={LOUDNORM_TARGET}"
        print("[ffmpeg pass 2] dynamic loudnorm (measurement unavailable, e.g. silent input)")

    cmd = base_cmd + [
        "-filter_complex", f"{pre_filter};[mixout]{loudnorm}[out]",
        "-map", "[out]",
        "-t", f"{total_s:.3f}",
        "-ar", "44100",
        "-b:a", "128k",
        str(output_path),
    ]

    print("[ffmpeg]", " ".join(cmd))
    _run_ffmpeg(ffmpeg, cmd)

    done = AudioSegment.from_file(output_path)
    print(f"final mix: {output_path} ({len(done) / 1000:.1f}s)")
    return output_path
