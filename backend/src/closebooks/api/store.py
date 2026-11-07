"""What the server holds: the runs folder, opened runs (a few at a time) and the phases they refer to."""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import orjson

from .errors import Problem, not_found
from .jobs import Jobs, check_ident, default_command
from .phase_data import PhaseData
from .run_data import RunData

MAX_OPEN_RUNS = 3


class Store:
    def __init__(self, runs_dir: Path, command=default_command, served: str | None = None):
        self.runs_dir = runs_dir
        self.served = served  # the one run `serve` was started on: the only one opened ahead of time
        self.jobs = Jobs(runs_dir, command)
        self._runs: OrderedDict[str, RunData] = OrderedDict()
        self._phases: dict[str, PhaseData] = {}
        self._lock = threading.Lock()

    def run_ids(self) -> list[str]:
        """Folders with a run.json, most recent first."""
        metas = []
        for folder in self.runs_dir.glob("*/run.json"):
            try:
                metas.append((orjson.loads(folder.read_bytes())["createdAt"], folder.parent.name))
            except (orjson.JSONDecodeError, KeyError):
                continue
        return [name for _, name in sorted(metas, reverse=True)]

    def run_meta(self, run_id: str) -> dict:
        check_ident(run_id, "runId")
        path = self.runs_dir / run_id / "run.json"
        if not path.exists():
            raise not_found("Run", run_id)
        return {**orjson.loads(path.read_bytes()), "runId": run_id}  # the folder is the id, not what run.json says

    def official_result(self, run_id: str) -> dict | None:
        """The leaderboard's answer, when a person saved it next to the submission (CONTRACT §2.9)."""
        path = self.runs_dir / run_id / "live_result.json"
        if not path.exists():
            return None
        result = orjson.loads(path.read_bytes())
        metrics = {k: v for k, v in (result.get("metrics") or {}).items() if isinstance(v, (int, float))}
        return {"score": result["score"], "createdAt": result["created_at"], "metrics": metrics}

    def run(self, run_id: str) -> RunData:
        self.run_meta(run_id)
        with self._lock:  # one build at a time: it is a few seconds and the next caller wants its result
            if run_id in self._runs:
                self._runs.move_to_end(run_id)
                return self._runs[run_id]
            data = RunData(self.runs_dir / run_id)
            self._runs[run_id] = data
            while len(self._runs) > MAX_OPEN_RUNS:
                self._runs.popitem(last=False)
            return data

    def preload(self, run_id: str) -> None:
        """Open the run and build the package tables its screens read, so no request pays for their build."""
        phase = self.phase(self.run(run_id).phase)
        phase.accounts()
        phase.ensure_items()
        phase.documents()
        phase.detail_files()

    def phase(self, name: str) -> PhaseData:
        check_ident(name, "phase")
        with self._lock:
            if name not in self._phases:
                try:
                    self._phases[name] = PhaseData(name)
                except FileNotFoundError as exc:
                    raise Problem(404, "Phase not found", str(exc)) from exc
            return self._phases[name]

    def latest_run_of(self, phase: str) -> Path | None:
        for run_id in self.run_ids():
            if self.run_meta(run_id)["phase"] == phase:
                return self.runs_dir / run_id
        return None
