import os
import shutil
from pathlib import Path


def _ensure_ffmpeg_on_path() -> None:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    suffix = ".exe" if os.name == "nt" else ""
    home = Path.home()
    candidates = [
        home / "miniconda3" / "Library" / "bin",
        home / "miniconda3" / "bin",
        home / "anaconda3" / "Library" / "bin",
        home / "miniconda3" / "envs" / "*",
    ]
    for c in candidates:
        for d in sorted(c.parent.glob(c.name)) if c.name == "*" else [c]:
            if (d / f"ffmpeg{suffix}").exists() and (d / f"ffprobe{suffix}").exists():
                os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
                return


_ensure_ffmpeg_on_path()
