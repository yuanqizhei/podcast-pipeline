from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from src.assemble import assemble
from src.mix import mix
from src.parser import parse, write_timeline
from src.tts import get_provider, synthesize_timeline

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "script"
AUDIO = ROOT / "audio"
SEGMENTS = AUDIO / "segments"
OUTPUT = AUDIO / "output"

COMMANDS = ("build", "tts", "assemble", "mix")
TERMINAL_STATES = ("done", "failed", "cancelled")


class JobCancelled(Exception):
    pass


def preflight(provider: str) -> list[str]:
    errors: list[str] = []
    if provider != "minimax":
        return errors
    if not os.environ.get("MINIMAX_API_KEY") or not os.environ.get("MINIMAX_GROUP_ID"):
        errors.append("MINIMAX_API_KEY / MINIMAX_GROUP_ID not set in .env")
    if not os.environ.get("MINIMAX_VOICE_ID"):
        errors.append("MINIMAX_VOICE_ID empty; clone a voice first (Voice Clone page)")
    return errors


def _limit_items(items, limit: int):
    out = []
    seen = 0
    for item in items:
        if item.type == "speech":
            seen += 1
            if seen > limit:
                break
        out.append(item)
    return out


@dataclass
class Job:
    id: str
    script: str
    command: str
    provider: str
    limit: int | None = None
    force: bool = False
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    stage: str = ""
    progress: dict = field(default_factory=dict)
    error: str | None = None
    logs: deque = field(default_factory=lambda: deque(maxlen=2000))
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _subs: list = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def to_dict(self, include_logs: bool = False) -> dict:
        d = {
            "id": self.id,
            "script": self.script,
            "command": self.command,
            "provider": self.provider,
            "limit": self.limit,
            "force": self.force,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stage": self.stage,
            "progress": dict(self.progress),
            "error": self.error,
        }
        if include_logs:
            d["logs"] = list(self.logs)
        return d


class JobManager:
    """Sequential background job runner: one pipeline task at a time."""

    MAX_KEPT = 50

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._queue: queue.Queue = queue.Queue()
        self._mutex = threading.Lock()
        threading.Thread(target=self._worker, daemon=True, name="job-worker").start()

    # -- public API -------------------------------------------------------

    def submit(self, script: str, command: str, provider: str, limit: int | None, force: bool) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:8],
            script=script,
            command=command,
            provider=provider,
            limit=limit,
            force=force,
        )
        with self._mutex:
            self._jobs[job.id] = job
            self._order.append(job.id)
            while len(self._order) > self.MAX_KEPT:
                old = self._order.pop(0)
                self._jobs.pop(old, None)
        self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._mutex:
            return self._jobs.get(job_id)

    def recent(self, n: int = 20) -> list[Job]:
        with self._mutex:
            ids = self._order[-n:][::-1]
            return [self._jobs[i] for i in ids if i in self._jobs]

    def current_running(self) -> Job | None:
        with self._mutex:
            for j in self._jobs.values():
                if j.status == "running":
                    return j
        return None

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        if job.status in ("queued", "running"):
            job.cancel_event.set()
            if job.status == "queued":
                job.status = "cancelled"
                job.finished_at = time.time()
                self._emit(job, {"kind": "job_done", "status": "cancelled"})
            return True
        return False

    def subscribe(self, job_id: str) -> "queue.Queue | None":
        job = self.get(job_id)
        if job is None:
            return None
        q: queue.Queue = queue.Queue()
        with job._lock:
            q.put({"kind": "snapshot", "job": job.to_dict(include_logs=True), "ts": time.time()})
            job._subs.append(q)
        return q

    def unsubscribe(self, job_id: str, q) -> None:
        job = self.get(job_id)
        if job is None:
            return
        with job._lock:
            if q in job._subs:
                job._subs.remove(q)

    # -- internals --------------------------------------------------------

    def _worker(self):
        while True:
            job_id = self._queue.get()
            job = self.get(job_id)
            if job is None or job.status != "queued":
                continue
            self._run(job)

    def _emit(self, job: Job, event: dict) -> None:
        ts = time.time()
        with job._lock:
            if event.get("kind") == "log":
                job.logs.append({"ts": ts, "message": event.get("message", "")})
            entry = dict(event)
            entry["ts"] = ts
            entry["job_id"] = job.id
            for q in list(job._subs):
                q.put(entry)

    def _run(self, job: Job):
        job.status = "running"
        job.started_at = time.time()
        self._emit(job, {"kind": "job_started"})
        self._emit(job, {"kind": "log", "message": f"job {job.command} start: {job.script} (provider={job.provider})"})
        try:
            script_path = SCRIPTS / f"{job.script}.txt"
            if not script_path.exists():
                raise RuntimeError(f"script not found: {script_path.name}")

            tl = parse(script_path, AUDIO)
            write_timeline(tl, OUTPUT / f"{tl.episode}_timeline.json")
            if job.limit:
                tl.items = _limit_items(tl.items, job.limit)
                self._emit(job, {"kind": "log", "message": f"[preview] limited to first {job.limit} speech blocks"})

            def on_event(ev: dict):
                if job.cancel_event.is_set():
                    raise JobCancelled()
                kind = ev.get("kind")
                if kind == "start":
                    job.stage = ev["stage"]
                    job.progress = {}
                elif kind == "progress":
                    job.stage = ev["stage"]
                    job.progress = {
                        "current": ev.get("current"),
                        "total": ev.get("total"),
                        "percent": ev.get("percent"),
                        "id": ev.get("id"),
                        "cached": ev.get("cached"),
                    }
                self._emit(job, ev)

            voice = beds = None
            if job.command in ("tts", "build"):
                provider = get_provider(job.provider)
                synthesize_timeline(tl, SEGMENTS, provider, force=job.force, on_event=on_event)
            if job.command in ("assemble", "build"):
                if job.cancel_event.is_set():
                    raise JobCancelled()
                voice, beds = assemble(tl, SEGMENTS, OUTPUT, on_event=on_event)
            if job.command in ("mix", "build"):
                if job.cancel_event.is_set():
                    raise JobCancelled()
                if voice is None:
                    voice = OUTPUT / "voice_track.wav"
                    beds = OUTPUT / "beds.json"
                    if not voice.exists() or not beds.exists():
                        raise RuntimeError("voice_track.wav / beds.json not found; run build or assemble first")
                    info = json.loads(Path(beds).read_text(encoding="utf-8"))
                    built_for = info.get("episode")
                    if built_for and built_for != job.script:
                        raise RuntimeError(
                            f"intermediate tracks were built for '{built_for}', not '{job.script}'; run assemble/build for this episode first"
                        )
                out_path = OUTPUT / f"{job.script}_final.mp3"
                mix(voice, beds, out_path, on_event=on_event)
            job.status = "done"
            self._emit(job, {"kind": "log", "message": f"job {job.command} done: {job.script}"})
        except JobCancelled:
            job.status = "cancelled"
            job.error = "cancelled by user"
            self._emit(job, {"kind": "log", "message": "job cancelled"})
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            job.error = str(e)
            self._emit(job, {"kind": "log", "message": f"[error] {e}"})
        finally:
            job.finished_at = time.time()
            self._emit(job, {"kind": "job_done", "status": job.status})


manager = JobManager()
