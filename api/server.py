"""ACCORD console API (CONTRACTS.md §4).

MOCK=1: serves docs/fixtures/* and replays run_events.jsonl (~600 ms between events).
Live:   uses core.bundle + agents.coordinator.Coordinator as the event producer.

Both modes go through RunManager, so the UI cannot tell them apart.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
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


def load_config() -> dict:
    try:
        from core.config import load_config as _load  # type: ignore

        return _load(str(ROOT / "config.yaml"))
    except Exception:
        with open(ROOT / "config.yaml") as f:
            return yaml.safe_load(f)


CONFIG = load_config()
RUNS_DIR = ROOT / CONFIG.get("paths", {}).get("runs_dir", "runs")
HERO_DIR = ROOT / CONFIG.get("paths", {}).get("hero_cache_dir", "api/hero_cache")
EVAL_PATH = ROOT / CONFIG.get("paths", {}).get("eval_results", "eval/results.json")
MODELS = {k: CONFIG["models"][k] for k in ("ATC", "PILOT", "GROUND", "NARRATOR")}


# ---------------------------------------------------------------- helpers

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{secrets.token_hex(3)}"


def canonical_json(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256((entry["prev_hash"] + canonical_json(body)).encode("utf-8")).hexdigest()


def verify_entries(entries: list[dict]) -> dict:
    """VerifyResult (§5), stdlib only. Swap for core.log.verify_chain at integration."""
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


# ---------------------------------------------------------------- runs

class Run:
    def __init__(self, run_id: str, scenario_id: str, parent_run_id: str | None, chaos: list[dict]):
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.parent_run_id = parent_run_id
        self.chaos = chaos
        self.events: list[dict] = []
        self.subscribers: set[asyncio.Queue] = set()
        self.log_entries: list[dict] = []   # mock only; live mode reads runs/<run_id>.jsonl
        self.coordinator: Any = None
        self.task: asyncio.Task | None = None
        self.started = False

    def publish(self, env: dict) -> None:
        self.events.append(env)
        for q in list(self.subscribers):
            q.put_nowait(env)


class RunManager:
    """Holds per-run event lists and one asyncio.Queue per subscriber. Producers call run.publish()."""

    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}
        self.llm_enabled = True

    def create(self, scenario_id: str, chaos: list[dict] | None = None, parent_run_id: str | None = None) -> Run:
        run = Run(new_run_id(), scenario_id, parent_run_id, chaos or [])
        if MOCK:
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
            producer = self._mock_producer if MOCK else self._live_producer
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

    # ---- mock producer: replays the fixture stream

    async def _mock_producer(self, run: Run) -> None:
        fixture = read_jsonl(FIXTURES / "run_events.jsonl")
        if not self.llm_enabled:
            fixture = self._mock_fallback_stream(fixture)
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

    @staticmethod
    def _mock_fallback_stream(fixture: list[dict]) -> list[dict]:
        """LLM killed in mock mode: run_started, options, fallback, awaiting_approval, run_ended."""
        by_type: dict[str, dict] = {}
        for e in fixture:
            by_type.setdefault(e["type"], e)
        opts = by_type["options"]["data"]
        result = opts["fallback"]
        plan = next((o for o in opts["options"] if o["option_id"] == result["option_id"]), None)
        base = {k: by_type["run_started"][k] for k in ("run_id", "log_hash")}
        mk = lambda t, d: {**base, "type": t, "data": d}  # noqa: E731
        return [
            by_type["run_started"],
            by_type["options"],
            mk("fallback", {"reason": "LLM_KILLED", "result": result, "plan": plan}),
            mk("awaiting_approval", {"decision_source": "FALLBACK", "option_id": result["option_id"], "rounds_used": 0}),
            mk("run_ended", {"final_state": "FALLBACK", "rounds_used": 0, "latency_ms": 12,
                             "chain_ok": True, "n_llm_calls": 0}),
        ]

    # ---- live producer: the coordinator

    async def _live_producer(self, run: Run) -> None:
        try:
            from agents.coordinator import Coordinator  # type: ignore
            from core.bundle import build_bundle  # type: ignore
            from core.types import ChaosEvent  # type: ignore

            chaos = [ChaosEvent(**c) for c in run.chaos] or None
            bundle = build_bundle(run.scenario_id, chaos=chaos)
            run.coordinator = Coordinator(bundle, run.run_id, config=CONFIG)
            async for env in run.coordinator.run():
                if env.get("type") == "run_started":
                    env["data"]["parent_run_id"] = run.parent_run_id
                run.publish(env)
        except Exception as exc:  # surface to the UI instead of hanging the stream
            run.publish({"type": "error", "run_id": run.run_id, "seq": len(run.events), "ts": now_iso(),
                         "log_hash": "", "data": {"message": f"{type(exc).__name__}: {exc}", "fatal": True}})

    # ---- approve

    async def approve(self, run: Run, action: str, option_id: str, by: str, note: str) -> dict:
        if MOCK:
            prev = run.log_entries[-1] if run.log_entries else None
            payload = {"action": action, "option_id": option_id, "by": by, "note": note}
            entry = {
                "seq": len(run.log_entries),
                "ts": now_iso(),
                "run_id": prev["run_id"] if prev else run.run_id,
                "scenario_id": prev["scenario_id"] if prev else run.scenario_id,
                "source_row": prev["source_row"] if prev else {},
                "event_type": "approved",
                "actor": "HUMAN",
                "constraint_ids": [],
                "synthetic_fields": [],
                "payload": payload,
                "prev_hash": prev["hash"] if prev else "0" * 64,
            }
            entry["hash"] = entry_hash(entry)
            run.log_entries.append(entry)
            final_hash = entry["hash"]
            run.publish({"type": "approved", "run_id": run.run_id, "seq": len(run.events), "ts": entry["ts"],
                         "log_hash": final_hash, "data": {**payload, "final_hash": final_hash}})
            return {"ok": True, "final_hash": final_hash}
        if run.coordinator is None:
            raise HTTPException(409, "run has not produced a decision yet")
        res = await run.coordinator.approve(action, option_id, by, note)
        # the coordinator yields `approved` on its own stream only while run() is iterating; push it if not
        if not any(e["type"] == "approved" for e in run.events) and isinstance(res, dict) and "event" in res:
            run.publish(res["event"])
        return {"ok": bool(res.get("ok", True)), "final_hash": res.get("final_hash", "")}


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


class ApproveRequest(BaseModel):
    action: str
    option_id: str
    by: str
    note: str = ""


class KillRequest(BaseModel):
    llm_enabled: bool


def _llm_enabled() -> bool:
    if MOCK:
        return manager.llm_enabled
    try:
        from agents.killswitch import llm_enabled  # type: ignore

        return llm_enabled()
    except Exception:
        return manager.llm_enabled


@app.get("/api/health")
def health() -> dict:
    data_loaded = MOCK or (ROOT / CONFIG["paths"]["qualifying"]).exists()
    return {"ok": True, "llm_enabled": _llm_enabled(), "models": MODELS, "data_loaded": data_loaded, "mock": MOCK}


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

    return [s.model_dump(mode="json") for s in list_scenarios(limit=limit, airport=airport, date=date)]


@app.get("/api/scenarios/{scenario_id}")
def scenario(scenario_id: str) -> dict:
    if MOCK:
        return read_json(FIXTURES / "scenario_bundle.json")
    from core.bundle import build_bundle  # type: ignore
    from core.mapdata import map_payload  # type: ignore

    b = build_bundle(scenario_id)
    return {"bundle": b.model_dump(mode="json"), "map": map_payload(b.scenario).model_dump(mode="json")}


@app.post("/api/runs")
def create_run(req: RunRequest) -> dict:
    run = manager.create(req.scenario_id, req.chaos, req.parent_run_id)
    return {"run_id": run.run_id}


@app.get("/api/runs/{run_id}/stream")
async def stream(run_id: str, request: Request):
    run = manager.get(run_id)

    async def gen():
        async for env in manager.subscribe(run):
            if await request.is_disconnected():
                break
            yield {"event": env["type"], "data": json.dumps(env, ensure_ascii=False)}

    return EventSourceResponse(gen(), ping=15)


@app.post("/api/runs/{run_id}/chaos")
def chaos(run_id: str, ev: dict) -> dict:
    parent = manager.get(run_id)
    child = manager.create(parent.scenario_id, parent.chaos + [ev], parent_run_id=parent.run_id)
    return {"run_id": child.run_id, "parent_run_id": parent.run_id}


@app.post("/api/runs/{run_id}/approve")
async def approve(run_id: str, req: ApproveRequest) -> dict:
    return await manager.approve(manager.get(run_id), req.action, req.option_id, req.by, req.note)


@app.post("/api/kill")
def kill(req: KillRequest) -> dict:
    manager.llm_enabled = req.llm_enabled
    if not MOCK:
        try:
            from agents.killswitch import set_llm_enabled  # type: ignore

            set_llm_enabled(req.llm_enabled)
        except Exception:
            pass
    return {"llm_enabled": _llm_enabled()}


def _log_entries(run: Run) -> list[dict]:
    if MOCK:
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
    if not MOCK:
        try:
            from core.log import verify_chain  # type: ignore

            return verify_chain(str(RUNS_DIR / f"{run_id}.jsonl")).model_dump(mode="json")
        except ImportError:
            pass
    return verify_entries(_log_entries(run))


@app.get("/api/runs/{run_id}/record")
def record(run_id: str) -> PlainTextResponse:
    run = manager.get(run_id)
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


@app.get("/api/replay/{name}/stream")
async def replay(name: str, request: Request):
    path = HERO_DIR / f"{Path(name).name}.jsonl"
    if not path.exists():
        raise HTTPException(404, f"no hero cache {name}")
    events = read_jsonl(path)

    async def gen():
        for env in events:
            if await request.is_disconnected():
                break
            yield {"event": env["type"], "data": json.dumps(env, ensure_ascii=False)}
            await asyncio.sleep(MOCK_GAP_S)

    return EventSourceResponse(gen(), ping=15)


# ---- serve the built console at /
DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
