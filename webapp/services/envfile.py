from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / ".env"


def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_PATH.exists():
        return out
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def update_env(mapping: dict[str, str]) -> None:
    """Persist key=value pairs into .env (replace in place / append at the end)
    and mirror them into the current process environment so the change takes
    effect immediately without a restart."""
    if not mapping:
        return
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    remaining = dict(mapping)
    new_lines: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else None
        if key in remaining:
            new_lines.append(f"{key}={remaining.pop(key)}")
        else:
            new_lines.append(line)
    for k, v in remaining.items():
        new_lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    for k, v in mapping.items():
        os.environ[k] = v


def remove_env(keys: list[str]) -> None:
    """Drop keys from .env and the current process environment (restore to
    code defaults)."""
    if not keys:
        return
    drop = set(keys)
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    kept = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else None
        if key in drop:
            continue
        kept.append(line)
    ENV_PATH.write_text("\n".join(kept) + "\n", encoding="utf-8")
    for k in drop:
        os.environ.pop(k, None)


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]
