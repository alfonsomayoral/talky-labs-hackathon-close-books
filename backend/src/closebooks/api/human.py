"""runs/<id>/human/*.jsonl: the only place the platform writes. Appends are serialised by a file lock."""
from __future__ import annotations

import fcntl
import re
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import orjson

_PROCESS_LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_jsonl(path: Path) -> list[dict]:
    """Missing or empty files are fine; an unfinished last line (a write in flight) is skipped."""
    if not path.exists():
        return []
    records = []
    for line in path.read_bytes().splitlines():
        if line.strip():
            try:
                records.append(orjson.loads(line))
            except orjson.JSONDecodeError:
                continue
    return records


class HumanFiles:
    def __init__(self, run_dir: Path):
        self.dir = run_dir / "human"

    def read(self, name: str) -> list[dict]:
        return read_jsonl(self.dir / name)

    @contextmanager
    def locked(self):
        """Exclusive across threads and processes (a `closebooks run` may read while we append)."""
        self.dir.mkdir(exist_ok=True)
        with _PROCESS_LOCK, (self.dir / ".lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def append(self, name: str, record: dict) -> None:
        """Call inside `locked()` when the record depends on what the file already has."""
        with self.locked(), (self.dir / name).open("ab") as handle:
            handle.write(orjson.dumps(record) + b"\n")

    def append_with_id(self, name: str, make: callable) -> dict:
        """`make(existing_records)` builds the new record, e.g. with the next sequential id."""
        with self.locked():
            record = make(self.read(name))
            with (self.dir / name).open("ab") as handle:
                handle.write(orjson.dumps(record) + b"\n")
        return record


def next_id(prefix: str, key: str, existing: list[dict], width: int) -> str:
    numbers = [int(m.group(1)) for r in existing if (m := re.search(r"(\d+)$", str(r.get(key, ""))))]
    return f"{prefix}{max(numbers, default=0) + 1:0{width}d}"


# ── Decisions → case status ──────────────────────────────────────────────────

ACTION_STATUS = {"done": "done", "manual": "done", "review": "needs_review"}


def case_statuses(decisions: list[dict]) -> dict[str, str]:
    """Latest decision per case wins. An answered question closes the case."""
    out: dict[str, str] = {}
    for d in decisions:
        out[d["caseId"]] = ACTION_STATUS[d["action"]] if "action" in d else "done"
    return out


def answered_questions(decisions: list[dict]) -> dict[str, dict]:
    return {d["questionId"]: d for d in decisions if d.get("questionId")}


# ── Drafts: outbox lines override the backend's draft, last line wins ───────

def apply_outbox(drafts: list[dict], outbox: list[dict]) -> list[dict]:
    latest = {o["draftId"]: o for o in outbox}
    merged = []
    for d in drafts:
        o = latest.get(d["draftId"])
        merged.append({**d, **{k: o[k] for k in ("subject", "body", "to", "attachments") if k in o},
                       "status": o["status"]} if o else d)
    return merged


# ── Memory rules ─────────────────────────────────────────────────────────────

REQUIRED = {
    "payer_is_customer": ("partyId",),
    "reference_alias": ("pattern",),
    "supplier_nets_credit_notes": ("partyId",),
    "always_category": ("category",),
    "ignore_suffix": ("partyId", "regex"),
    "parent_pays": ("payerPartyId", "forPartyId"),
}
ANY_OF = {
    "payer_is_customer": ("payerName", "iban"),
    "reference_alias": ("documentNumber", "partyId"),
    "always_category": ("bank", "bankCode", "bankSubcode", "textPattern"),
}


def validate_rule(kind: str, params: dict, categories: set[str]) -> str | None:
    """A message if the rule is malformed, else None."""
    missing = [k for k in REQUIRED[kind] if not params.get(k)]
    if missing:
        return f"{kind} needs params: {', '.join(missing)}"
    if kind in ANY_OF and not any(params.get(k) for k in ANY_OF[kind]):
        return f"{kind} needs at least one of: {', '.join(ANY_OF[kind])}"
    if kind == "always_category" and params["category"] not in categories:
        return f"Unknown category {params['category']!r}"
    for key in ("regex", "pattern", "textPattern"):
        if params.get(key):
            try:
                re.compile(params[key])
            except re.error as exc:
                return f"{key} is not a valid regular expression: {exc}"
    return None


def active_rules(lines: list[dict]) -> list[dict]:
    """Last line per ruleId wins (a deletion appends the rule again with active=false)."""
    latest: dict[str, dict] = {}
    for line in lines:
        latest[line["ruleId"]] = line
    return [r for r in latest.values() if r.get("active", True)]
