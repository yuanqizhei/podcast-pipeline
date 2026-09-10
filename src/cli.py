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
SEGMENTS.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)

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


def _limit_items(items, limit: int | None):
    if not limit:
        return items
    out = []
    seen = 0
    for item in items:
        if item.type == "speech":
            seen += 1
            if seen > limit:
                break
        out.append(item)
    return out


def _preflight(provider: str) -> None:
    if provider != "minimax":
        return
    fatal = False
    missing = [k for k in ("MINIMAX_API_KEY", "MINIMAX_GROUP_ID") if not os.environ.get(k)]
    if missing and not (ROOT / ".env").exists():
        print("[error] .env not found; copy .env.example -> .env and fill in your keys")
        fatal = True
    elif missing:
        print(f"[error] missing in .env: {', '.join(missing)} (get them at https://platform.minimaxi.com)")
        fatal = True
    if not os.environ.get("MINIMAX_VOICE_ID"):
        print("[error] MINIMAX_VOICE_ID empty; record a 1-min sample and run: python -m src.cli clone <sample.wav>")
        fatal = True
    if fatal:
        raise SystemExit(1)


def cmd_tts(args):
    provider = args.provider or os.environ.get("TTS_PROVIDER", "dryrun")
    _preflight(provider)
    tl = _load_tl(args.script)
    if args.limit:
        tl.items = _limit_items(tl.items, args.limit)
        print(f"[preview] limited to first {args.limit} speech blocks")
    paths = synthesize_timeline(tl, SEGMENTS, get_provider(provider), force=args.force)
    print(f"tts done ({provider}): {len(paths)} segments in {SEGMENTS / tl.episode}")


def cmd_assemble(args):
    tl = _load_tl(args.script)
    assemble(tl, SEGMENTS, OUTPUT, AUDIO)


def cmd_mix(args):
    voice = OUTPUT / "voice_track.wav"
    beds = OUTPUT / "beds.json"
    if not voice.exists() or not beds.exists():
        raise RuntimeError(f"voice_track.wav / beds.json not found in {OUTPUT}; run build or assemble first")
    import json

    info = json.loads(beds.read_text(encoding="utf-8"))
    built_for = info.get("episode")
    if built_for and built_for != args.script.stem:
        raise RuntimeError(
            f"intermediate tracks were built for '{built_for}', not '{args.script.stem}'; run assemble/build for this episode first"
        )
    out = OUTPUT / f"{args.script.stem}_final.mp3"
    mix(voice, beds, out, AUDIO)


def cmd_build(args):
    provider = args.provider or os.environ.get("TTS_PROVIDER", "dryrun")
    _preflight(provider)
    tl = _load_tl(args.script)
    if args.limit:
        tl.items = _limit_items(tl.items, args.limit)
        print(f"[preview] limited to first {args.limit} speech blocks")
    synthesize_timeline(tl, SEGMENTS, get_provider(provider), force=args.force)
    voice, beds = assemble(tl, SEGMENTS, OUTPUT, AUDIO)
    out = OUTPUT / f"{args.script.stem}_final.mp3"
    mix(voice, beds, out, AUDIO)


def cmd_clone(args):
    if not args.sample.exists():
        raise RuntimeError(f"voice sample not found: {args.sample}")
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
    p.add_argument("--limit", type=int, help="only synthesize first N speech blocks (preview)")
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
    p.add_argument("--limit", type=int, help="preview: only first N speech blocks")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("clone", help="upload voice sample to minimax, save voice_id")
    p.add_argument("sample", type=Path)
    p.set_defaults(func=cmd_clone)

    args = ap.parse_args()
    try:
        args.func(args)
    except (RuntimeError, ValueError) as e:
        print(f"[error] {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
