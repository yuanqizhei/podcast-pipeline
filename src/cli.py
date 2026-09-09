from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .assemble import assemble
from .mix import mix
from .parser import parse, write_timeline, load_timeline, hash_script
from .tts import get_provider, synthesize_timeline, MiniMaxProvider

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "audio"
SEGMENTS = AUDIO / "segments"
OUTPUT = AUDIO / "output"

load_dotenv(ROOT / ".env")


def timeline_path(script: Path) -> Path:
    return OUTPUT / f"{script.stem}_timeline.json"


def cmd_parse(args):
    tl = parse(args.script.resolve())
    out = timeline_path(args.script)
    write_timeline(tl, out)
    speech = sum(1 for i in tl.items if i.type == "speech")
    chars = sum(len(i.text) for i in tl.items if i.type == "speech")
    print(f"parsed {args.script.name}: {speech} speech blocks, {chars} chars -> {out}")


def _load_tl(script: Path):
    tp = timeline_path(script)
    if tp.exists():
        tl = load_timeline(tp)
        # stale cache (script edited since last parse, or old timeline without
        # a hash) would silently drop script changes -> re-parse on mismatch
        if tl.script_hash and tl.script_hash == hash_script(script.resolve()):
            return tl
        print(f"[parse] script changed since last parse, refreshing {tp.name}")
    tl = parse(script.resolve())
    write_timeline(tl, tp)
    return tl


def cmd_tts(args):
    tl = _load_tl(args.script)
    provider = args.provider or os.environ.get("TTS_PROVIDER", "dryrun")
    paths = synthesize_timeline(tl.items, SEGMENTS, get_provider(provider), force=args.force)
    print(f"tts done ({provider}): {len(paths)} segments in {SEGMENTS}")


def cmd_assemble(args):
    tl = _load_tl(args.script)
    assemble(tl, SEGMENTS, OUTPUT, AUDIO)


def cmd_mix(args):
    voice = OUTPUT / "voice_track.wav"
    beds = OUTPUT / "beds.json"
    out = OUTPUT / f"{args.script.stem}_final.mp3"
    mix(voice, beds, out, AUDIO)


def cmd_build(args):
    tl = _load_tl(args.script)
    provider = args.provider or os.environ.get("TTS_PROVIDER", "dryrun")
    synthesize_timeline(tl.items, SEGMENTS, get_provider(provider), force=args.force)
    voice, beds = assemble(tl, SEGMENTS, OUTPUT, AUDIO)
    out = OUTPUT / f"{args.script.stem}_final.mp3"
    mix(voice, beds, out, AUDIO)


def cmd_clone(args):
    prov = MiniMaxProvider.__new__(MiniMaxProvider)
    prov.api_key = os.environ.get("MINIMAX_API_KEY", "")
    prov.group_id = os.environ.get("MINIMAX_GROUP_ID", "")
    if not prov.api_key or not prov.group_id:
        raise RuntimeError("MINIMAX_API_KEY / MINIMAX_GROUP_ID not set in .env")
    voice_id = prov.clone_voice(args.sample.resolve())
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    kept = [l for l in lines if not l.startswith("MINIMAX_VOICE_ID=")]
    kept.append(f"MINIMAX_VOICE_ID={voice_id}")
    env_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"voice cloned: {voice_id} (saved to .env)")


def main():
    ap = argparse.ArgumentParser(prog="podcast", description="podcast pipeline: script -> tts -> mix")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse", help="parse annotated script into timeline json")
    p.add_argument("script", type=Path)
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("tts", help="synthesize speech segments")
    p.add_argument("script", type=Path)
    p.add_argument("--provider", choices=["dryrun", "minimax"])
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("assemble", help="assemble voice track with pauses/inserts")
    p.add_argument("script", type=Path)
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser("mix", help="final ffmpeg mix with beds + loudnorm")
    p.add_argument("script", type=Path)
    p.set_defaults(func=cmd_mix)

    p = sub.add_parser("build", help="full pipeline: tts -> assemble -> mix")
    p.add_argument("script", type=Path)
    p.add_argument("--provider", choices=["dryrun", "minimax"])
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("clone", help="upload voice sample to minimax, save voice_id")
    p.add_argument("sample", type=Path)
    p.set_defaults(func=cmd_clone)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
