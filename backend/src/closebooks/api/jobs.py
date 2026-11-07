"""`closebooks run` in the background, one at a time. The run folder is the pipeline's; we only read it."""
from __future__ import annotations

import queue
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import orjson

from .. import paths
from .errors import Problem
from .human import now_iso

IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def check_ident(value: str, what: str) -> str:
    if not IDENT.match(value) or ".." in value:
        raise Problem(422, "Invalid request", f"{what} must be letters, digits, dot, dash or underscore")
    return value


def with_memory(command: list[str], out: Path) -> list[str]:
    """A run started with memoryFrom carries its rules in human/: the pipeline must apply them, not only keep them."""
    human = out / "human"
    return [*command, "--memory", str(human)] if (human / "memory_rules.jsonl").exists() else command


def default_command(phase: str, out: Path) -> list[str]:
    return [sys.executable, "-m", "closebooks.cli", "run", "--phase", phase, "--out", str(out)]


class Job:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.status = "queued"
        self.started_at = now_iso()
        self.finished_at: str | None = None
        self.error: str | None = None


class Jobs:
    def __init__(self, runs_dir: Path, command: Callable[[str, Path], list[str]] = default_command):
        self.runs_dir, self.command = runs_dir, command
        self.jobs: dict[str, Job] = {}
        self._queue: queue.Queue[tuple[Job, str]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    def submit(self, phase: str, memory_rules: Path | None) -> Job:
        check_ident(phase, "phase")
        try:
            paths.phase_dir(phase)
        except FileNotFoundError as exc:
            raise Problem(404, "Phase not found", str(exc)) from exc
        with self._lock:
            stamp = f"{phase}-{datetime.now():%Y%m%d-%H%M%S}"
            run_id, n = stamp, 1
            while run_id in self.jobs or (self.runs_dir / run_id).exists():
                n += 1
                run_id = f"{stamp}-{n}"
            job = Job(run_id)
            self.jobs[run_id] = job
            if memory_rules is not None:
                human = self.runs_dir / run_id / "human"
                human.mkdir(parents=True)
                shutil.copyfile(memory_rules, human / "memory_rules.jsonl")
            self._queue.put((job, phase))
            if self._worker is None:
                self._worker = threading.Thread(target=self._work, daemon=True)
                self._worker.start()
        return job

    def _work(self) -> None:
        while True:
            job, phase = self._queue.get()
            job.status = "running"
            out = self.runs_dir / job.run_id
            done = subprocess.run(with_memory(self.command(phase, out), out), capture_output=True, text=True,
                                  cwd=paths.ROOT)
            if done.returncode == 0 and (self.runs_dir / job.run_id / "run.json").exists():
                job.status = "done"
            else:
                job.status, job.error = "failed", (done.stderr or done.stdout).strip()[-2000:] or "no output"
            job.finished_at = now_iso()

    def status(self, run_id: str) -> dict | None:
        """RunStatus of a job of this process, or of a finished folder; None if the run does not exist."""
        folder = self.runs_dir / run_id
        job = self.jobs.get(run_id)
        meta = orjson.loads((folder / "run.json").read_bytes()) if (folder / "run.json").exists() else None
        if job is None:
            if meta is None:
                if not folder.is_dir():
                    return None
                return {"runId": run_id, "status": "failed", "stage": None, "stages": {}, "startedAt": now_iso(),
                        "finishedAt": None, "error": "The folder has no run.json and no job of this server"}
            return {"runId": run_id, "status": "done", "stage": None, "stages": meta["stages"],
                    "startedAt": meta["createdAt"], "finishedAt": meta["createdAt"], "error": None}
        stage = None
        if job.status == "running":
            stage = "output" if (folder / "submission.csv.gz").exists() else "load"
        return {"runId": run_id, "status": job.status, "stage": stage, "stages": meta["stages"] if meta else {},
                "startedAt": job.started_at, "finishedAt": job.finished_at, "error": job.error}
