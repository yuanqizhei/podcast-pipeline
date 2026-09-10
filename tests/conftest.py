"""Shared fixtures: isolate every test run inside a temp project directory
(scripts/audio/.env/data) so the real project is never touched."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """Redirect all module-level path constants to a temp workspace."""
    audio = tmp_path / "audio"
    segments = audio / "segments"
    output = audio / "output"
    scripts = tmp_path / "script"
    data = tmp_path / "data"
    for d in (audio, segments, output, scripts, data):
        d.mkdir(parents=True, exist_ok=True)
    env_path = tmp_path / ".env"

    import webapp.api.assets as api_assets
    import webapp.api.outputs as api_outputs
    import webapp.api.scripts as api_scripts
    import webapp.api.voice as api_voice
    import webapp.services.envfile as envfile
    import webapp.services.runner as runner

    patches = {
        runner: dict(ROOT=tmp_path, SCRIPTS=scripts, AUDIO=audio, SEGMENTS=segments,
                     OUTPUT=output, DATA_DIR=data, JOBS_LOG=data / "jobs.jsonl"),
        envfile: dict(ROOT=tmp_path, ENV_PATH=env_path),
        api_scripts: dict(SCRIPTS=scripts, AUDIO=audio, SEGMENTS=segments, OUTPUT=output),
        api_outputs: dict(OUTPUT=output, SCRIPTS=scripts, SEGMENTS=segments),
        api_assets: dict(AUDIO=audio),
        api_voice: dict(ROOT=tmp_path, ENV_PATH=env_path),
    }
    for mod, attrs in patches.items():
        for key, value in attrs.items():
            monkeypatch.setattr(mod, key, value)
    # drop stale parse cache between tests (keys are absolute paths, but be safe)
    api_scripts._parse_cache.clear()
    return tmp_path


@pytest.fixture
def client(tmp_project):
    from webapp import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
