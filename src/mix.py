from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from pydub import AudioSegment


def check_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH; install it first (winget install Gyan.FFmpeg)")
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


def mix(voice_path: Path, beds_path: Path, output_path: Path) -> Path:
    ffmpeg = check_ffmpeg()
    info = json.loads(beds_path.read_text(encoding="utf-8"))
    all_beds = info["beds"]
    total_s = info["total_ms"] / 1000
    beds = [b for b in all_beds if Path(b["file"]).exists()]
    for b in all_beds:
        if b not in beds:
            print(f"[warn] bed asset missing, skipped: {b['file']}")

    cmd = [ffmpeg, "-y", "-i", str(voice_path)]
    for bed in beds:
        cmd += ["-stream_loop", "-1", "-i", str(bed["file"])]

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
            bg = f"[{labels[0]}"
        chains.append(
            f"{bg}[0:a]sidechaincompress=threshold=0.03:ratio=8:attack=50:release=600[ducked]"
        )
        final_mix = "[ducked]"
        chains.append(
            f"{final_mix}[0:a]amix=inputs=2:duration=longest,volume=2.0,"
            "alimiter=limit=0.95,"
            "loudnorm=I=-16:TP=-1.5:LRA=11[out]"
        )
    else:
        chains.append(
            f"{final_mix}alimiter=limit=0.95,"
            "loudnorm=I=-16:TP=-1.5:LRA=11[out]"
        )
    filter_complex = ";".join(chains)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-t", f"{total_s:.3f}",
        "-ar", "44100",
        "-b:a", "128k",
        str(output_path),
    ]

    print("[ffmpeg]", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")

    done = AudioSegment.from_file(output_path)
    print(f"final mix: {output_path} ({len(done) / 1000:.1f}s)")
    return output_path
