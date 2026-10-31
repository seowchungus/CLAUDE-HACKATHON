"""Hash-chained, append-only consensus log (CONTRACTS.md §5).

Each line of runs/<run_id>.jsonl is a LogEntry. hash = sha256(prev_hash + canonical_json(entry without "hash")).
Seq 0 is always "scenario_loaded" with payload {scenario: Scenario}, written by the constructor for a new file.
If runs/<run_id>.jsonl already exists the log resumes from its head (never truncates).
"""
import hashlib
import json
import os
import threading
from datetime import datetime, timezone

from core.config import repo_path
from core.types import LogEntry, Scenario, VerifyResult

GENESIS_HASH = "0" * 64


def canonical_json(x) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256((entry["prev_hash"] + canonical_json(body)).encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def source_row_of(s: Scenario) -> dict:
    r = s.row
    return {"date": f"{r.year:04d}-{r.month:02d}-{r.day:02d}", "airline": r.airline,
            "flight_number": r.flight_number}


class ConsensusLog:
    def __init__(self, run_id: str, scenario: Scenario, runs_dir: str = "runs"):
        self.run_id = run_id
        self.scenario_id = scenario.scenario_id
        self._source_row = source_row_of(scenario)
        self._entries: list[LogEntry] = []
        self._lock = threading.Lock()
        self._dir = repo_path(runs_dir)
        os.makedirs(self._dir, exist_ok=True)
        self._path = os.path.join(self._dir, f"{run_id}.jsonl")
        if os.path.exists(self._path) and os.path.getsize(self._path) > 0:
            with open(self._path, encoding="utf-8") as f:
                self._entries = [LogEntry.model_validate(json.loads(line)) for line in f if line.strip()]
            return
        open(self._path, "w", encoding="utf-8").close()
        synthetic = [k for k, v in scenario.provenance.items() if v == "synthetic"]
        self._write("scenario_loaded", "SYSTEM", {"scenario": scenario.model_dump(mode="json")}, [], synthetic)

    def _last_raw_hash(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS_HASH

    def _write(self, event_type: str, actor: str, payload: dict,
               constraint_ids: list[str], synthetic_fields: list[str]) -> LogEntry:
        with self._lock:
            prev = self._last_raw_hash()
            e = {"seq": len(self._entries), "ts": _now_iso(), "run_id": self.run_id,
                 "scenario_id": self.scenario_id, "source_row": self._source_row,
                 "event_type": event_type, "actor": actor, "constraint_ids": list(constraint_ids),
                 "synthetic_fields": list(synthetic_fields),
                 "payload": json.loads(json.dumps(payload, default=_json_default)), "prev_hash": prev}
            e["hash"] = entry_hash(e)
            entry = LogEntry.model_validate(e)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                f.flush()
            self._entries.append(entry)
            return entry

    def append(self, event_type: str, actor: str, payload: dict,
               constraint_ids: list[str] | None = None) -> LogEntry:
        return self._write(event_type, actor, payload, constraint_ids or [], [])

    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    def head_hash(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS_HASH

    @property
    def path(self) -> str:
        return self._path


def _json_default(o):
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def verify_chain(path: str) -> VerifyResult:
    """Recompute every hash. broken_at = seq (line index) of the first bad entry, else None."""
    prev = GENESIS_HASH
    n = 0
    with open(repo_path(path), encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                ok = (e.get("seq") == i and e.get("prev_hash") == prev and e.get("hash") == entry_hash(e))
            except (ValueError, KeyError, TypeError):
                ok = False
            if not ok:
                return VerifyResult(ok=False, n_entries=n, head_hash=prev, broken_at=i)
            prev = e["hash"]
            n += 1
    return VerifyResult(ok=True, n_entries=n, head_hash=prev, broken_at=None)
