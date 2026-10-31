"""ACCORD console API (CONTRACTS.md §4, v1.2).

MOCK=1 (no data, no key, never calls Gemini):
  - plain runs replay docs/fixtures/run_events.jsonl (~600 ms between events)
  - chaos children and scripted `mode` runs drive the real Coordinator with MockLLMClient
    on the fixture scenario (chaos applied with core.chaos), paced like the replay
Live: core.bundle + agents.coordinator.Coordinator as the producer.

Every mode goes through RunManager, so the UI cannot tell them apart.
"""
from __future__ import annotations

import asyncio
import copy
import csv
import functools
import hashlib
import itertools
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "docs" / "fixtures"
MOCK = os.environ.get("MOCK", "0") == "1"
MOCK_GAP_S = float(os.environ.get("MOCK_GAP_S", "0.6"))
REPLAY_MAX_GAP_S = 1.5
SCRIPTED_MODES = ("deadlock", "unsafe", "hallucinate")
# INT-01 quota freeze: ACCORD_LLM=mock runs every coordinator run (real data) on scripted MockLLMClient, never Gemini
# pitch heroes, pinned at the top of the default scenario list (W3-07); both are in tests/golden and the hero cache
HERO_IDS = ("2015-12-30_DL2463_ICT-ATL", "2015-03-02_OO6476_AUS-SFO")
FORCE_MOCK_LLM = os.environ.get("ACCORD_LLM", "").lower() == "mock"


def load_config() -> dict:
    try:
        from core.config import load_config as _load  # type: ignore

        return _load(str(ROOT / "config.yaml"))
    except Exception:
        with open(ROOT / "config.yaml") as f:
            return yaml.safe_load(f)


CONFIG = load_config()
PATHS = CONFIG.get("paths", {})
RUNS_DIR = ROOT / PATHS.get("runs_dir", "runs")
HERO_DIR = ROOT / PATHS.get("hero_cache_dir", "api/hero_cache")
EVAL_PATH = ROOT / PATHS.get("eval_results", "eval/results.json")
LIMITS_PATH = ROOT / CONFIG.get("workbook", {}).get("extracted", "data/airport_limits.json")
MODELS = {k: CONFIG["models"][k] for k in ("ATC", "PILOT", "GROUND", "NARRATOR")}


# ---------------------------------------------------------------- helpers

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{secrets.token_hex(3)}"


def canonical_json(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256((entry["prev_hash"] + canonical_json(body)).encode("utf-8")).hexdigest()


def verify_entries(entries: list[dict]) -> dict:
    """VerifyResult (§5), stdlib only (same formula as core.log.verify_chain)."""
    prev = "0" * 64
    for i, e in enumerate(entries):
        if e.get("seq") != i or e.get("prev_hash") != prev or entry_hash(e) != e.get("hash"):
            return {"ok": False, "n_entries": len(entries), "head_hash": prev, "broken_at": i}
        prev = e["hash"]
    return {"ok": True, "n_entries": len(entries), "head_hash": prev, "broken_at": None}


def read_jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def read_json(path: Path) -> Any:
    with open(path) as f:
        return json.load(f)


def envelope(run_id: str, seq: int, type_: str, data: dict, log_hash: str = "") -> dict:
    return {"type": type_, "run_id": run_id, "seq": seq, "ts": now_iso(), "log_hash": log_hash, "data": data}


def mock_scenario_ids() -> set[str]:
    return {s["scenario_id"] for s in read_json(FIXTURES / "scenarios_list.json")}


# ---------------------------------------------------------------- runs

class Run:
    def __init__(self, run_id: str, scenario_id: str, parent_run_id: str | None, chaos: list[dict],
                 mode: str | None):
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.parent_run_id = parent_run_id
        self.chaos = chaos
        self.mode = mode
        self.events: list[dict] = []
        self.subscribers: set[asyncio.Queue] = set()
        self.log_entries: list[dict] = []   # fixture replay only; coordinator runs write runs/<run_id>.jsonl
        self.bundle_payload: dict | None = None
        self.coordinator: Any = None
        self.task: asyncio.Task | None = None
        self.started = False

    @property
    def replays_fixture(self) -> bool:
        return MOCK and not self.chaos and not self.mode

    def has(self, type_: str) -> bool:
        return any(e["type"] == type_ for e in self.events)

    def last(self, type_: str) -> dict | None:
        return next((e for e in reversed(self.events) if e["type"] == type_), None)

    def publish(self, env: dict) -> None:
        self.events.append(env)
        for q in list(self.subscribers):
            q.put_nowait(env)


class RunManager:
    """Holds per-run event lists and one asyncio.Queue per subscriber. Producers call run.publish()."""

    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}
        self.llm_enabled = True

    def create(self, scenario_id: str, chaos: list[dict] | None = None, parent_run_id: str | None = None,
               mode: str | None = None) -> Run:
        if MOCK and scenario_id not in mock_scenario_ids():
            raise HTTPException(404, f"unknown scenario {scenario_id}")
        if mode is not None and mode not in SCRIPTED_MODES:
            raise HTTPException(422, f"mode must be one of {SCRIPTED_MODES}")
        run = Run(new_run_id(), scenario_id, parent_run_id, chaos or [], mode)
        if run.replays_fixture:
            run.log_entries = read_jsonl(FIXTURES / "run_log.jsonl")
        self.runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> Run:
        run = self.runs.get(run_id)
        if run is None:
            raise HTTPException(404, f"unknown run {run_id}")
        return run

    def ensure_started(self, run: Run) -> None:
        if not run.started:
            run.started = True
            producer = self._mock_producer if run.replays_fixture else self._coordinator_producer
            run.task = asyncio.create_task(producer(run))

    async def subscribe(self, run: Run) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue()
        backlog = list(run.events)
        run.subscribers.add(q)
        self.ensure_started(run)
        try:
            for env in backlog:
                yield env
            seen = len(backlog)
            while True:
                env = await q.get()
                if env["seq"] < seen:
                    continue
                seen = env["seq"] + 1
                yield env
        finally:
            run.subscribers.discard(q)

    # ---- bundles

    def bundle(self, run: Run) -> dict:
        """{bundle, map} for this run's own (possibly chaos-mutated) scenario."""
        if run.bundle_payload is None:
            if run.replays_fixture:
                run.bundle_payload = read_json(FIXTURES / "scenario_bundle.json")
            else:
                b = self._build_bundle(run)
                from core.mapdata import map_payload  # type: ignore

                run.bundle_payload = {"bundle": b.model_dump(mode="json"),
                                      "map": map_payload(b.scenario).model_dump(mode="json")}
        return run.bundle_payload

    @staticmethod
    def _build_bundle(run: Run):
        from core.types import ChaosEvent  # type: ignore

        chaos = [ChaosEvent(**c) for c in run.chaos]
        if not MOCK:
            from core.bundle import build_bundle  # type: ignore

            return build_bundle(run.scenario_id, chaos=chaos or None)
        from core.bundle import build_bundle_from_scenario  # type: ignore
        from core.chaos import apply_chaos  # type: ignore
        from core.types import ScenarioBundle  # type: ignore

        b = ScenarioBundle.model_validate(read_json(FIXTURES / "scenario_bundle.json")["bundle"])
        if not chaos:
            return b
        s = b.scenario
        for ev in chaos:
            s = apply_chaos(s, ev)
        return build_bundle_from_scenario(s)

    # ---- in-memory chain for fixture-replay runs

    @staticmethod
    def _logged_upto(run: Run) -> int:
        """Number of log entries covering what has been published (seq 0 scenario_loaded + one per event)."""
        hashes = [e["log_hash"] for e in run.events]
        idx = {e["hash"]: i for i, e in enumerate(run.log_entries)}
        return max((idx[h] + 1 for h in hashes if h in idx), default=1)

    @staticmethod
    def _append_mock_log(run: Run, event_type: str, actor: str, payload: dict, cids: list[str] | None = None) -> dict:
        prev = run.log_entries[-1]
        entry = {"seq": len(run.log_entries), "ts": now_iso(), "run_id": prev["run_id"],
                 "scenario_id": prev["scenario_id"], "source_row": prev["source_row"],
                 "event_type": event_type, "actor": actor, "constraint_ids": cids or [], "synthetic_fields": [],
                 "payload": copy.deepcopy(payload), "prev_hash": prev["hash"]}
        entry["hash"] = entry_hash(entry)
        run.log_entries.append(entry)
        return entry

    # ---- producer 1: fixture replay (MOCK, plain runs)

    async def _mock_producer(self, run: Run) -> None:
        fixture = read_jsonl(FIXTURES / "run_events.jsonl")
        if not self.llm_enabled:
            await self._mock_fallback(run, fixture)
            return
        for i, env in enumerate(fixture):
            env = copy.deepcopy(env)
            env["run_id"] = run.run_id
            env["seq"] = i
            env["ts"] = now_iso()
            if env["type"] == "run_started":
                env["data"]["parent_run_id"] = run.parent_run_id
                env["data"]["chaos_applied"] = run.chaos
                env["data"]["llm_enabled"] = self.llm_enabled
            run.publish(env)
            await asyncio.sleep(MOCK_GAP_S)

    async def _mock_fallback(self, run: Run, fixture: list[dict]) -> None:
        """LLM killed, fixture replay: run_started, options, fallback, awaiting_approval, run_ended,
        each with its own entry in a fresh in-memory chain (seq 0 = the fixture's scenario_loaded)."""
        first = {}
        for e in fixture:
            first.setdefault(e["type"], e)
        started = {**first["run_started"]["data"], "llm_enabled": False, "parent_run_id": run.parent_run_id,
                   "chaos_applied": run.chaos}
        opts = first["options"]["data"]
        result = opts["fallback"]
        plan = next((o for o in opts["options"] if o["option_id"] == result["option_id"]), None)
        run.log_entries = run.log_entries[:1]
        steps = [
            ("run_started", "COORDINATOR", started, []),
            ("options", "CHECKER", opts, [c for c in ("H1_wake_separation", "H2_runway_capacity", "H3_fuel_reserve",
                                                      "H4_gate_validity", "H5_crew_duty", "H6_taxiway_reachability",
                                                      "H7_severe_turbulence")]),
            ("fallback", "FALLBACK", {"reason": "LLM_KILLED", "result": result, "plan": plan}, []),
            ("awaiting_approval", "COORDINATOR",
             {"decision_source": "FALLBACK", "option_id": result["option_id"], "rounds_used": 0}, []),
            ("run_ended", "COORDINATOR", {"final_state": "FALLBACK", "rounds_used": 0, "latency_ms": 12,
                                          "chain_ok": True, "n_llm_calls": 0}, []),
        ]
        for type_, actor, data, cids in steps:
            entry = self._append_mock_log(run, type_, actor, data, cids)
            run.publish(envelope(run.run_id, len(run.events), type_, data, log_hash=entry["hash"]))
            await asyncio.sleep(MOCK_GAP_S)

    # ---- producer 2: the coordinator (MOCK: MockLLMClient on the fixture scenario; live: default client)

    async def _coordinator_producer(self, run: Run) -> None:
        try:
            from agents.coordinator import Coordinator  # type: ignore

            b = self._build_bundle(run)
            llm = None  # live: the coordinator's default (Gemini behind the budget guard)
            if MOCK or run.mode or FORCE_MOCK_LLM:
                from agents.client import make_llm  # type: ignore

                mode = run.mode if run.mode not in (None, "live") else "mock"
                llm = make_llm(mode, config=CONFIG)  # scripted mock agents, never Gemini
            run.coordinator = Coordinator(b, run.run_id, config=CONFIG, llm=llm, parent_run_id=run.parent_run_id)
            async for env in run.coordinator.run():  # published exactly as logged (log_hash must match)
                run.publish(env)
                if MOCK:
                    await asyncio.sleep(MOCK_GAP_S)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # surface to the UI instead of hanging the stream
            run.publish(envelope(run.run_id, len(run.events), "error",
                                 {"message": f"{type(exc).__name__}: {exc}", "fatal": True}))

    # ---- chaos: supersede a running parent

    async def supersede(self, run: Run) -> None:
        if run.has("run_ended"):
            return
        c = run.coordinator
        if c is not None:
            try:
                await c.cancel(reason="SUPERSEDED")  # False if it had already finished: it keeps its own ending
            except Exception:
                pass
            if run.task and not run.task.done():  # stop pacing; flush everything the coordinator logged
                run.task.cancel()
            for env in c.envelopes[len(run.events):]:
                run.publish(env)
        elif run.task and not run.task.done():
            run.task.cancel()
        if not run.has("run_ended"):  # fixture replay: no coordinator; logged in the in-memory chain
            data = {"final_state": "SUPERSEDED", "rounds_used": (run.last("round_started") or {}).get("data", {}).get("round", 0),
                    "latency_ms": 0, "chain_ok": True, "n_llm_calls": 0}
            run.log_entries = run.log_entries[:self._logged_upto(run)]
            entry = self._append_mock_log(run, "run_ended", "COORDINATOR", data)
            run.publish(envelope(run.run_id, len(run.events), "run_ended", data, log_hash=entry["hash"]))

    # ---- approve (v1.1 rules)

    async def approve(self, run: Run, action: str, option_id: str, by: str, note: str) -> dict:
        awaiting = run.last("awaiting_approval")
        if awaiting is None:
            raise HTTPException(409, "run is not awaiting approval")
        if run.has("approved"):
            raise HTTPException(409, "run already signed off")
        if awaiting["data"]["decision_source"] == "ESCALATE" and action != "OVERRIDE":
            raise HTTPException(409, "ESCALATE: only OVERRIDE with an explicit option_id is allowed")
        if action not in ("APPROVE", "OVERRIDE") or not option_id:
            raise HTTPException(422, "action must be APPROVE|OVERRIDE with an option_id")

        if run.replays_fixture:
            # mirror Coordinator.approve: the checker overrides the human too
            checks: dict = {}
            for ev in run.events:
                if ev["type"] == "options":
                    checks.update(ev["data"].get("checks") or {})
                elif ev["type"] == "counter_checked" and ev["data"].get("accepted") and ev["data"].get("check"):
                    checks[ev["data"]["option_id"]] = ev["data"]["check"]
            if option_id not in checks or option_id == "opt_fcfs":
                raise HTTPException(400, f"unknown option {option_id}")
            if not checks[option_id].get("feasible"):
                failed = [r["constraint_id"] for r in checks[option_id].get("results", []) if not r.get("passed")]
                raise HTTPException(400, f"{option_id} is infeasible: fails {', '.join(failed)}")
            if action == "APPROVE" and option_id != awaiting["data"].get("option_id"):
                raise HTTPException(400, "APPROVE must name the decided option; use OVERRIDE to pick another")
            signed = run.log_entries[-1]["hash"]
            payload = {"action": action, "option_id": option_id, "by": by, "note": note, "final_hash": signed}
            entry = self._append_mock_log(run, "approved", "HUMAN", payload)
            run.publish(envelope(run.run_id, len(run.events), "approved", payload, log_hash=entry["hash"]))
            return {"ok": True, "final_hash": signed}

        c = run.coordinator
        if c is None:
            raise HTTPException(409, "run has no coordinator")
        res = await c.approve(action, option_id, by, note)
        if not res.get("ok"):
            raise HTTPException(int(res.get("code") or 409), res.get("error") or "approval refused")
        if c.approved and not run.has("approved"):
            run.publish(c.approved)
        return {"ok": True, "final_hash": res["final_hash"]}


manager = RunManager()

# ---------------------------------------------------------------- app

app = FastAPI(title="ACCORD console API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    scenario_id: str
    chaos: list[dict] | None = None
    parent_run_id: str | None = None
    mode: str | None = None          # additive (W3-03): scripted MockLLMClient modes


class ApproveRequest(BaseModel):
    action: str
    option_id: str
    by: str
    note: str = ""


class KillRequest(BaseModel):
    llm_enabled: bool


def _killswitch():
    try:
        from agents import killswitch  # type: ignore

        return killswitch
    except Exception:
        return None


def _llm_enabled() -> bool:
    ks = _killswitch()
    return ks.llm_enabled() if ks else manager.llm_enabled


MOCK_BUDGET = {
    "keys": {"GEMINI_API_KEY": {"used_today": 223, "cap": 480, "remaining": 257, "rpm_cap": 12}},
    "enforce": True,
    "resets_at": "2026-11-01T07:00:00Z",
}


def _llm_budget() -> dict | None:
    if MOCK:
        return MOCK_BUDGET
    try:
        from agents.budget import budget_status  # type: ignore

        return budget_status().model_dump(mode="json")
    except Exception:
        return None


@app.get("/api/health")
def health() -> dict:
    data_loaded = MOCK or (ROOT / PATHS["qualifying"]).exists()
    return {"ok": True, "llm_enabled": _llm_enabled(), "models": MODELS, "data_loaded": data_loaded,
            "mock": MOCK, "llm_budget": _llm_budget()}


@app.get("/api/limits")
def limits(scenario_id: str | None = None) -> dict:
    th = CONFIG.get("thresholds", {})
    neg = CONFIG.get("negotiation", {})
    workbook = {
        "wake_separation": th.get("wake_separation_s", {}),
        "fuel_and_crew": {k: th[k] for k in ("fuel_final_reserve_min", "fuel_spare_on_arrival_min", "fuel_burn_kg_per_h",
                                             "contingency_fuel_pct", "flight_crew_max_duty_min", "ground_shift_min",
                                             "ground_overtime_cost_multiplier") if k in th},
        "rules_of_play": {"max_rounds": neg.get("MAX_ROUNDS"), "gate_change_notice_min": th.get("gate_change_notice_min"),
                          "arrival_share_of_runway_ops": th.get("arrival_share_of_runway_ops"),
                          "turbulence_severe": th.get("turbulence_severe")},
    }
    airport = None
    if MOCK:
        fx = read_json(FIXTURES / "scenario_bundle.json")["bundle"]["scenario"]
        airport = fx.get("airport_limits") or None
        scenario_id = scenario_id or fx["scenario_id"]  # pre-v1.2 fixture: look its destination up in the table
    dest = scenario_id.rsplit("-", 1)[-1] if scenario_id else None
    if airport is None and dest and LIMITS_PATH.exists():
        try:
            table = read_json(LIMITS_PATH)
            airport = table.get(dest) or (table.get("airports") or {}).get(dest)
        except Exception:
            airport = None
    return {"workbook": workbook, "airport": airport, "deviations": CONFIG.get("workbook_deviations", [])}


@functools.lru_cache(maxsize=1)
def _hero_summaries() -> tuple[dict, ...]:
    from core.scenario import _find_row, _summary  # type: ignore

    out = []
    for sid in HERO_IDS:
        try:
            out.append({**_summary(_find_row(sid)).model_dump(mode="json"), "hero": True})
        except Exception:
            pass  # a hero missing from this data set is simply not pinned
    return tuple(out)


@app.get("/api/scenarios")
def scenarios(limit: int = 50, airport: str | None = None, date: str | None = None) -> list:
    if MOCK:
        items = read_json(FIXTURES / "scenarios_list.json")
        if airport:
            items = [s for s in items if airport in (s["origin"], s["destination"])]
        if date:
            items = [s for s in items if s["date"] == date]
        return items[:limit]
    from core.scenario import list_scenarios  # type: ignore

    items = [s.model_dump(mode="json") for s in list_scenarios(limit=limit, airport=airport, date=date)]
    if not airport and not date:  # heroes pinned first (W3-07)
        heroes = list(_hero_summaries())
        items = heroes + [s for s in items if s["scenario_id"] not in {h["scenario_id"] for h in heroes}]
    return items[: limit + len(HERO_IDS)]


# ---- "pick any row of flights.csv" (W3-07)

FLIGHTS_CSV = ROOT / PATHS.get("raw_dir", "data/raw") / "flights.csv"


def _csv_to_row(rec: dict) -> dict:
    def n(x: str) -> int:
        try:
            return int(float(x)) if x not in ("", None) else 0
        except ValueError:
            return 0

    return {"DATE": f"{int(rec['YEAR']):04d}-{int(rec['MONTH']):02d}-{int(rec['DAY']):02d}", "AIRLINE": rec["AIRLINE"],
            "FLIGHT_NUMBER": int(rec["FLIGHT_NUMBER"]), "ORIGIN_AIRPORT": rec["ORIGIN_AIRPORT"],
            "DESTINATION_AIRPORT": rec["DESTINATION_AIRPORT"], "WEATHER_DELAY": n(rec["WEATHER_DELAY"]),
            "LATE_AIRCRAFT_DELAY": n(rec["LATE_AIRCRAFT_DELAY"])}


def _read_csv_row(row: int) -> dict | None:
    with open(FLIGHTS_CSV, newline="") as f:
        rec = next(itertools.islice(csv.DictReader(f), row, row + 1), None)
    return _csv_to_row(rec) if rec else None


@app.get("/api/scenarios/by_row/{row}")
def scenario_by_row(row: int) -> dict:
    """ScenarioSummary (+ `row`) for the 0-based data row `row` of data/raw/flights.csv. 404 out of range;
    422 if the row is not a qualifying disruption (WEATHER_DELAY > 15 or LATE_AIRCRAFT_DELAY > 20)."""
    if MOCK:
        raise HTTPException(404, "by_row needs the real data set (not available in MOCK)")
    if row < 0:
        raise HTTPException(404, f"row {row} out of range")
    from core.scenario import _find_row, _summary  # type: ignore

    sm = None
    try:
        from core.scenario import scenario_id_for_row  # type: ignore  # W1-09

        got = scenario_id_for_row(row)
        sid = got if isinstance(got, str) else got.scenario_id
        sm = _summary(_find_row(sid))
    except ImportError:
        pass  # W1-09 not landed: stub on the raw CSV below
    except (IndexError, KeyError, ValueError, LookupError) as exc:
        raise HTTPException(404, f"row {row}: {exc}")
    if sm is None:
        r = _read_csv_row(row)
        if r is None:
            raise HTTPException(404, f"row {row} out of range")
        if not (r["WEATHER_DELAY"] > 15 or r["LATE_AIRCRAFT_DELAY"] > 20):
            raise HTTPException(422, f"row {row} ({r['AIRLINE']}{r['FLIGHT_NUMBER']} {r['DATE']}) is not a qualifying "
                                     "disruption (needs WEATHER_DELAY > 15 or LATE_AIRCRAFT_DELAY > 20)")
        sm = _summary(r)
    return {**sm.model_dump(mode="json"), "row": row}


@functools.lru_cache(maxsize=256)
def _csv_row_of(sid: str) -> int | None:
    from core.scenario import parse_scenario_id  # type: ignore

    date, airline, fn, origin, dest = parse_scenario_id(sid)
    y, m, d = (int(x) for x in date.split("-"))
    with open(FLIGHTS_CSV, newline="") as f:
        for i, rec in enumerate(csv.DictReader(f)):
            if (rec["FLIGHT_NUMBER"] == str(fn) and rec["AIRLINE"] == airline and rec["ORIGIN_AIRPORT"] == origin
                    and rec["DESTINATION_AIRPORT"] == dest and int(rec["DAY"]) == d and int(rec["MONTH"]) == m
                    and int(rec["YEAR"]) == y):
                return i
    return None


@app.get("/api/scenarios/{scenario_id}/csv_row")
def scenario_csv_row(scenario_id: str) -> dict:
    """0-based flights.csv row of a scenario (first match), for the 'flights.csv row N' label."""
    if MOCK:
        raise HTTPException(404, "no flights.csv in MOCK")
    try:
        row = _csv_row_of(scenario_id)
    except Exception:
        row = None
    if row is None:
        raise HTTPException(404, f"{scenario_id} not found in flights.csv")
    return {"scenario_id": scenario_id, "row": row}


@app.get("/api/scenarios/{scenario_id}")
def scenario(scenario_id: str) -> dict:
    if MOCK:
        if scenario_id not in mock_scenario_ids():
            raise HTTPException(404, f"unknown scenario {scenario_id}")
        return read_json(FIXTURES / "scenario_bundle.json")
    from core.bundle import build_bundle  # type: ignore
    from core.mapdata import map_payload  # type: ignore

    try:
        b = build_bundle(scenario_id)
    except (KeyError, ValueError, LookupError) as exc:
        raise HTTPException(404, f"unknown scenario {scenario_id}: {exc}")
    return {"bundle": b.model_dump(mode="json"), "map": map_payload(b.scenario).model_dump(mode="json")}


@app.post("/api/runs")
def create_run(req: RunRequest) -> dict:
    run = manager.create(req.scenario_id, req.chaos, req.parent_run_id, req.mode)
    return {"run_id": run.run_id}


@app.get("/api/runs/{run_id}/bundle")
def run_bundle(run_id: str) -> dict:
    return manager.bundle(manager.get(run_id))


@app.get("/api/runs/{run_id}/stream")
async def stream(run_id: str, request: Request):
    run = manager.get(run_id)

    async def gen():
        async for env in manager.subscribe(run):
            if await request.is_disconnected():
                break
            yield {"event": env["type"], "data": json.dumps(env, ensure_ascii=False)}

    return EventSourceResponse(gen(), ping=15)


try:
    from core.types import ChaosEvent  # type: ignore
except ImportError:  # core not importable: same shape as CONTRACTS §1
    from typing import Literal

    class ChaosEvent(BaseModel):  # type: ignore[no-redef]
        kind: Literal["RUNWAY_CLOSURE", "TAXIWAY_BLOCK", "GATE_FAILURE", "WEATHER_CELL"]
        params: dict = {}
        note: str = ""


@app.post("/api/runs/{run_id}/chaos")
async def chaos(run_id: str, ev: ChaosEvent) -> dict:
    parent = manager.get(run_id)
    child = manager.create(parent.scenario_id, parent.chaos + [ev.model_dump(mode="json")],
                           parent_run_id=parent.run_id, mode=parent.mode)
    if parent.started:
        await manager.supersede(parent)
    return {"run_id": child.run_id, "parent_run_id": parent.run_id}


@app.post("/api/runs/{run_id}/approve")
async def approve(run_id: str, req: ApproveRequest) -> dict:
    return await manager.approve(manager.get(run_id), req.action, req.option_id, req.by, req.note)


@app.post("/api/kill")
def kill(req: KillRequest) -> dict:
    manager.llm_enabled = req.llm_enabled
    ks = _killswitch()
    if ks:
        ks.set_llm_enabled(req.llm_enabled)
    return {"llm_enabled": _llm_enabled()}


def _log_entries(run: Run) -> list[dict]:
    if run.replays_fixture:
        return run.log_entries
    path = RUNS_DIR / f"{run.run_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, "log not written yet")
    return read_jsonl(path)


@app.get("/api/runs/{run_id}/log")
def log(run_id: str) -> Response:
    entries = _log_entries(manager.get(run_id))
    body = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
    return Response(body, media_type="application/x-ndjson",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}.jsonl"'})


@app.get("/api/runs/{run_id}/verify")
def verify(run_id: str) -> dict:
    run = manager.get(run_id)
    if not run.replays_fixture:
        try:
            from core.log import verify_chain  # type: ignore

            path = RUNS_DIR / f"{run_id}.jsonl"
            if not path.exists():
                raise HTTPException(404, "log not written yet")
            return verify_chain(str(path)).model_dump(mode="json")
        except ImportError:
            pass
    return verify_entries(_log_entries(run))


@app.get("/api/runs/{run_id}/record")
def record(run_id: str) -> PlainTextResponse:
    run = manager.get(run_id)
    try:
        from agents.narrator import record_markdown  # type: ignore
        from core.types import ScenarioBundle  # type: ignore

        b = ScenarioBundle.model_validate(manager.bundle(run)["bundle"])
        return PlainTextResponse(record_markdown(b, run.events, verify(run_id)["head_hash"]), media_type="text/markdown")
    except Exception:
        pass  # template below
    ev = {e["type"]: e["data"] for e in run.events}
    decision = ev.get("consensus") or ev.get("fallback") or {}
    plan = decision.get("plan") or {}
    ended = ev.get("run_ended", {})
    v = verify(run_id)
    lines = [
        f"# Resolution Record: {run.scenario_id}",
        "",
        f"- Run: `{run.run_id}`" + (f" (child of `{run.parent_run_id}`)" if run.parent_run_id else ""),
        f"- Outcome: **{ended.get('final_state', 'IN PROGRESS')}** after {ended.get('rounds_used', '?')} round(s)",
        f"- Plan: {plan.get('label', 'none')} (`{plan.get('option_id', '-')}`)",
        f"- Chaos applied: {', '.join(c.get('kind', '?') for c in run.chaos) or 'none'}",
        f"- Human sign-off: {ev['approved']['action'] + ' by ' + ev['approved']['by'] if 'approved' in ev else 'pending'}",
        f"- Log chain: {'verified' if v['ok'] else 'BROKEN at ' + str(v['broken_at'])} ({v['n_entries']} entries, head `{v['head_hash'][:12]}`)",
        "",
        ev.get("narration", {}).get("text", ""),
        "",
        "_Synthetic fields are labelled in the console; the DOT row is real._",
    ]
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


@app.get("/api/eval")
def eval_results() -> JSONResponse:
    if not EVAL_PATH.exists():
        raise HTTPException(404, "eval not run yet")
    return JSONResponse(read_json(EVAL_PATH))


@app.get("/api/replay")
def replay_list() -> list[str]:
    return sorted(p.stem for p in HERO_DIR.glob("*.jsonl")) if HERO_DIR.exists() else []


@app.get("/api/replay/{name}/stream")
async def replay(name: str, request: Request):
    path = HERO_DIR / f"{Path(name).name}.jsonl"
    if not path.exists():
        raise HTTPException(404, f"no hero cache {name}")
    events = read_jsonl(path)

    async def gen():
        prev: datetime | None = None
        for env in events:
            if await request.is_disconnected():
                break
            try:
                t = parse_iso(env["ts"])
                if prev is not None:  # original timing, capped
                    await asyncio.sleep(min(REPLAY_MAX_GAP_S, max(0.0, (t - prev).total_seconds())))
                prev = t
            except (KeyError, ValueError):
                await asyncio.sleep(MOCK_GAP_S)
            yield {"event": env["type"], "data": json.dumps(env, ensure_ascii=False)}
        while not await request.is_disconnected():  # keep open so the client doesn't auto-reconnect and replay again
            await asyncio.sleep(1)

    return EventSourceResponse(gen(), ping=15)


# ---- serve the built console at /
DIST = (ROOT / "web" / "dist").resolve()


def safe_dist_file(path: str) -> Path | None:
    """A file under DIST for this request path, or None. Rejects any path that resolves outside DIST
    (decoded ../, %2e%2e, absolute paths, symlinks out)."""
    try:
        f = (DIST / path).resolve()
    except (OSError, ValueError):
        return None
    return f if f.is_relative_to(DIST) and f.is_file() else None


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        return FileResponse(safe_dist_file(path) or DIST / "index.html")
