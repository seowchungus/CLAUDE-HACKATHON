"""Batch evaluation (proposal §8, CONTRACTS.md §6). Skeleton: B0 (FCFS) and B1 (optimiser) only, no LLM.

  python -m eval.run_eval [--n 30] [--llm none|mock|live] [--shard i/k] [--out PATH]
  python -m eval.run_eval --freeze [--n 30] [--seed 42]     (once; refuses if eval/eval_set.json exists)

Test set: read ONLY from the frozen eval/eval_set.json (sha256-checked): N qualifying rows, stratified by delay
type across the top-6 destination airports, excluding dev rows and every hero candidate ever listed or exported.
Every number written is measured; fields that were not run are null.

  --llm none|mock|live   none = B0/B1 only; mock = agents MockLLMClient (offline); live = Gemini (needs the
                         human's approval, --confirm-live and agents/budget.py)
  --keys 1,2,3 --shard i/k   split rows across teammates' keys; merge with python -m eval.merge_results
"""
import argparse
import asyncio
import hashlib
import json
import os
import random
import secrets
from datetime import datetime, timezone

import polars as pl

from core.bundle import build_bundle
from core.config import load_config, repo_path
from core.scenario import _qualifying, airports, dev_scenario_ids, make_scenario_id

N_AIRPORTS = 6


def hero_scenario_ids() -> list[str]:
    """Hero candidates (eval/pick_heroes.py) are demo rows, so they are excluded from the eval like dev rows."""
    try:
        with open(repo_path("eval/hero_candidates.json")) as fh:
            return [h["scenario_id"] for h in json.load(fh)["candidates"]]
    except (FileNotFoundError, KeyError, ValueError):
        return []


EVAL_SET = "eval/eval_set.json"
# Hero candidates of an earlier ranking (6cf34a4) that later dropped out of eval/hero_candidates.json; WN2433 was
# exported and on the board as a demo hero, so all three stay excluded from the held-out set.
FORMER_HEROES = ["2015-07-19_WN2433_SMF-LAX", "2015-11-09_OO6301_SNA-SFO", "2015-01-15_OO5242_DSM-DEN"]
SELECTION_RULE = ("qualifying rows (WEATHER_DELAY > 15 or LATE_AIRCRAFT_DELAY > 20) whose origin and destination "
                  "have coordinates; top-6 destinations by qualifying volume; per (airport, WEATHER_DELAY > 15 yes/no) "
                  "pool sorted by (DATE, AIRLINE, FLIGHT_NUMBER) and shuffled with random.Random(seed); round-robin "
                  "over airports, pick k is weather iff (k + k // 6) is even; excluded ids removed first")


def excluded_ids() -> list[str]:
    """Dev rows + every hero candidate ever listed or exported (current, former, golden files)."""
    gold = []
    d = repo_path("tests/golden")
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                gold.append(f[:-5])
    return sorted(set(dev_scenario_ids()) | set(hero_scenario_ids()) | set(FORMER_HEROES) | set(gold))


def _ids_sha256(ids: list[str]) -> str:
    return hashlib.sha256(json.dumps(ids).encode()).hexdigest()


def freeze_eval_set(n: int, seed: int) -> dict:
    """Write eval/eval_set.json once (refuses to overwrite: a frozen set is never re-drawn)."""
    path = repo_path(EVAL_SET)
    if os.path.exists(path):
        raise SystemExit(f"{EVAL_SET} already exists; the eval set is frozen")
    excl = excluded_ids()
    ids = select_test_set(n, seed, set(excl))
    q = _qualifying()
    s = {make_scenario_id(*r): w for *r, w in q.select(
        "DATE", "AIRLINE", "FLIGHT_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT",
        pl.col("WEATHER_DELAY").fill_null(0) > 15).rows()}
    res = {"frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
           "n": len(ids), "seed": seed, "selection_rule": SELECTION_RULE,
           "strata": {"weather": sum(bool(s.get(i)) for i in ids), "non_weather": sum(not s.get(i) for i in ids),
                      "airports": sorted({i.rsplit("-", 1)[1] for i in ids})},
           "scenario_ids": ids, "sha256": _ids_sha256(ids),
           "sha256_of": "hashlib.sha256(json.dumps(scenario_ids).encode()).hexdigest()",
           "excluded_ids": excl}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    return res


def load_eval_set() -> dict:
    """The frozen held-out set; the hash is checked so a hand-edited list is caught."""
    with open(repo_path(EVAL_SET)) as fh:
        es = json.load(fh)
    if _ids_sha256(es["scenario_ids"]) != es["sha256"]:
        raise SystemExit(f"{EVAL_SET}: sha256 mismatch, the frozen set was edited")
    return es


def select_test_set(n: int, seed: int, exclude: set[str] | None = None) -> list[str]:
    q = _qualifying()
    known = list(airports())
    q = q.filter(pl.col("ORIGIN_AIRPORT").is_in(known) & pl.col("DESTINATION_AIRPORT").is_in(known))
    top = (q.group_by("DESTINATION_AIRPORT").len().sort(["len", "DESTINATION_AIRPORT"], descending=[True, False])
           .head(N_AIRPORTS)["DESTINATION_AIRPORT"].to_list())
    rng = random.Random(seed)
    dev = exclude if exclude is not None else set(excluded_ids())
    weather = (pl.col("WEATHER_DELAY").fill_null(0) > 15)
    pools: dict[tuple[str, bool], list[str]] = {}
    for ap in top:
        sub = q.filter(pl.col("DESTINATION_AIRPORT") == ap).sort(["DATE", "AIRLINE", "FLIGHT_NUMBER"])
        for is_w in (True, False):
            rows = sub.filter(weather if is_w else ~weather).select(
                "DATE", "AIRLINE", "FLIGHT_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT").rows()
            ids = [make_scenario_id(*r) for r in rows]
            ids = [i for i in ids if i not in dev]
            rng.shuffle(ids)
            pools[(ap, is_w)] = ids
    out: list[str] = []
    k = 0
    while len(out) < n and any(pools.values()):
        ap, is_w = top[k % len(top)], (k + k // len(top)) % 2 == 0  # 15/15 at N=30, 5 per airport
        k += 1
        if pools[(ap, is_w)]:
            out.append(pools[(ap, is_w)].pop())
    return out


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def _pct(xs: list[float], q: float) -> int | None:
    if not xs:
        return None
    xs = sorted(xs)
    return int(xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))])


def _rate(rows: list[dict], pred) -> float | None:
    return round(sum(1 for r in rows if pred(r)) / len(rows), 3) if rows else None


def _new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{secrets.token_hex(3)}"


def make_llm(kind: str, keys: list[int] | None):
    """kind 'none' -> None (B0/B1 only), 'mock' -> agents MockLLMClient, 'live' -> GeminiClient restricted
    to the selected keys (1-based: 1=GEMINI_API_KEY, 2=_2, 3=_3)."""
    if kind == "none":
        return None
    if kind == "mock":
        from agents.client import MockLLMClient
        return MockLLMClient(config=load_config())
    try:
        import agents.budget  # noqa: F401  (the hard budget guard must exist before any live call)
    except ImportError as e:
        raise SystemExit("refusing --llm live: agents/budget.py (LLM budget guard, CONTRACTS §4.4) is missing") from e
    from agents.client import GeminiClient
    client = GeminiClient(load_config())
    if keys:
        names = [client.key_names[i - 1] for i in keys if 0 < i <= len(client.key_names)]
        client.key_names = names
        client._clients = {n: client._clients[n] for n in names}
        if not client._clients:
            raise SystemExit(f"none of keys {keys} are configured")
    return client


async def _negotiate(bundle, llm) -> dict:
    """Run the real coordinator on one bundle and extract every §8.3 metric from its event stream."""
    from agents.coordinator import Coordinator
    from core.constraints import check_option
    run_id = _new_run_id()
    coord = Coordinator(bundle, run_id, config=load_config(), llm=llm)
    ev: list[dict] = [e async for e in coord.run()]
    by = lambda t: [e["data"] for e in ev if e["type"] == t]  # noqa: E731
    ended = (by("run_ended") or [{}])[-1]
    msgs = by("agent_position")
    plan = None
    consensus_round = None
    if by("consensus"):
        c = by("consensus")[-1]
        plan, consensus_round = c["plan"], c["round"]
    elif by("fallback"):
        plan = by("fallback")[-1]["plan"]
    unsafe_blocked = sum(len(v["agents"]) for v in by("veto")) + sum(
        1 for c in by("counter_checked") if c.get("failed"))
    unsafe_exec = 0
    plan_metrics = None
    if plan is not None:
        from core.types import Option
        opt = Option.model_validate(plan)
        unsafe_exec = 0 if check_option(bundle.scenario, opt).feasible else 1  # re-checked independently
        plan_metrics = opt.metrics
    toks = [(m.get("tokens_in") or 0) + (m.get("tokens_out") or 0) for m in msgs]
    return {
        "run_id": run_id, "final_state": ended.get("final_state"), "rounds_used": ended.get("rounds_used"),
        "consensus_round": consensus_round, "option_id": plan["option_id"] if plan else None,
        "J": plan_metrics.cost_J if plan_metrics else None, "unsafe_blocked": unsafe_blocked,
        "unsafe_executed": unsafe_exec, "latency_ms": ended.get("latency_ms"),
        "n_llm_calls": ended.get("n_llm_calls"), "n_messages": len(msgs),
        "n_schema_fail": sum(1 for m in msgs if m.get("status") == "schema_fail"),
        "n_retried": sum(1 for m in msgs if (m.get("retries") or 0) > 0),
        "n_ok_positions": sum(1 for m in msgs if m.get("status") == "ok"),
        "n_ungrounded": sum(1 for m in msgs if m.get("status") == "ok" and m.get("ungrounded")),
        "tokens": sum(toks) if any(toks) else None,
        "plan_bank_delay_added_min": plan_metrics.bank_delay_added_min if plan_metrics else None,
        "plan_misconnected_pax": plan_metrics.misconnected_pax if plan_metrics else None,
        "plan_ramp_overtime_min": plan_metrics.ramp_overtime_min if plan_metrics else None,
    }


def evaluate_row(sid: str, llm) -> dict:
    try:
        b = build_bundle(sid)
    except Exception as e:  # noqa: BLE001 - record and continue; the eval must not die on one row
        return {"scenario_id": sid, "error": f"{type(e).__name__}: {e}"}
    f, m0 = b.fallback, b.fcfs.metrics
    row = {
        "scenario_id": sid, "final_state": None, "rounds_used": None, "option_id": None, "J": None,
        "J_B0": m0.cost_J, "J_B1": f.cost_J, "unsafe_blocked": None, "latency_ms": None, "run_id": None,
        "disruption_type": b.scenario.disruption_type, "destination": b.scenario.destination.iata,
        "B0_feasible": b.checks["opt_fcfs"].feasible, "B1_status": f.status, "B1_option_id": f.option_id,
        "n_options": len(b.options), "n_feasible": sum(b.checks[o.option_id].feasible for o in b.options),
        "B0_bank_delay_added_min": m0.bank_delay_added_min, "B0_misconnected_pax": m0.misconnected_pax,
        "B0_ramp_overtime_min": m0.ramp_overtime_min,
    }
    if llm is not None:
        try:
            row.update(asyncio.run(_negotiate(b, llm)))
        except Exception as e:  # noqa: BLE001
            row["error"] = f"negotiation {type(e).__name__}: {e}"
    return row


def summarize(per: list[dict], llm_kind: str) -> dict:
    ok = [p for p in per if "error" not in p]
    neg = [p for p in ok if p.get("final_state") is not None]
    msgs = sum(p.get("n_messages") or 0 for p in neg)
    planned = [p for p in neg if p.get("J") is not None]
    with_b1 = [p for p in planned if p.get("J_B1") is not None]

    def vs_b0(k: str) -> float | None:
        xs = [p[f"plan_{k}"] - p[f"B0_{k}"] for p in planned if p.get(f"plan_{k}") is not None]
        return _mean(xs)

    toks = [p["tokens"] for p in neg if p.get("tokens") is not None]
    return {
        "consensus_rate": _rate(neg, lambda p: p["final_state"] == "CONSENSUS"),
        "consensus_by_r2": _rate(neg, lambda p: p["final_state"] == "CONSENSUS" and (p["consensus_round"] or 9) <= 2),
        "consensus_by_r3": _rate(neg, lambda p: p["final_state"] == "CONSENSUS" and (p["consensus_round"] or 9) <= 3),
        "fallback_rate": _rate(neg, lambda p: p["final_state"] == "FALLBACK"),
        "escalate_rate": _rate(neg, lambda p: p["final_state"] == "ESCALATE"),
        "unsafe_proposals_blocked": sum(p["unsafe_blocked"] for p in neg) if neg else None,
        "unsafe_plans_executed": sum(p["unsafe_executed"] for p in neg) if neg else None,
        "schema_failure_rate": round(sum(p["n_schema_fail"] for p in neg) / msgs, 3) if msgs else None,
        "retry_rate": round(sum(p["n_retried"] for p in neg) / msgs, 3) if msgs else None,
        # ungrounded agent_positions / ok positions (rationale number not in a cited metric; flag only)
        "ungrounded_rate": (round(sum(p.get("n_ungrounded", 0) for p in neg)
                                  / sum(p.get("n_ok_positions", 0) for p in neg), 3)
                            if sum(p.get("n_ok_positions", 0) for p in neg) else None),
        "latency_p50_ms": _pct([p["latency_ms"] for p in neg if p.get("latency_ms") is not None], 0.5),
        "latency_p95_ms": _pct([p["latency_ms"] for p in neg if p.get("latency_ms") is not None], 0.95),
        "tokens_per_resolution": int(_mean(toks)) if toks else None,
        "J_mean": {"accord": _mean([p["J"] for p in planned]), "B0_fcfs": _mean([p["J_B0"] for p in ok]),
                   "B1_optimizer": _mean([p["J_B1"] for p in ok if p["J_B1"] is not None])},
        "regret_vs_B1_mean": _mean([p["J"] - p["J_B1"] for p in with_b1]),
        "vs_B0": {k: vs_b0(k) for k in ("bank_delay_added_min", "misconnected_pax", "ramp_overtime_min")},
        "B1_escalate_rate": _rate(ok, lambda p: p["B1_status"] == "ESCALATE"),
        "B0_infeasible_rate": _rate(ok, lambda p: not p["B0_feasible"]),
        "n_errors": len(per) - len(ok),
        "llm": llm_kind,
    }


def assemble(per: list[dict], seed: int, llm_kind: str, shard: str | None = None) -> dict:
    with open(repo_path("data/status_quo.json")) as fh:
        sq = json.load(fh)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "n": len([p for p in per if "error" not in p]), "n_dev": len(dev_scenario_ids()), "seed": seed,
        "status_quo": {k: sq[k] for k in ("qualifying_flights", "weather_delay_min", "late_aircraft_delay_min")},
        "summary": summarize(per, llm_kind),
        "ablations": {"B2_single_agent": None, "B3_model": None},
        "per_scenario": per,
        "measured": True,
        "llm": llm_kind,
        "shard": shard,
        "eval_set_sha256": load_eval_set()["sha256"],
        "bad_day": _bad_day(),
    }


def _bad_day() -> dict | None:
    """eval/bad_day.json (python -m eval.bad_day): deterministic B0/B1 baselines on the busiest hub-day."""
    try:
        with open(repo_path("eval/bad_day.json")) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


ROW_CALL_MARGIN = 10  # most calls one row can take: 3 rounds x 3 roles + a retry


def _used(key_index: int) -> int:
    from agents import budget
    name = "GEMINI_API_KEY" + ("" if key_index == 1 else f"_{key_index}")
    return budget.budget_status().keys[name]["used_today"]


def run(n: int, llm_kind: str = "none", keys: list[int] | None = None,
        shard: tuple[int, int] | None = None, stop_at_used: int | None = None) -> dict:
    es = load_eval_set()
    ids = es["scenario_ids"][:n]  # only the frozen set (n < 30 = its first n rows, for quick checks)
    if shard:
        i, k = shard
        ids = [sid for j, sid in enumerate(ids) if j % k == i - 1]
    llm = make_llm(llm_kind, keys)
    per = []
    for sid in ids:
        if stop_at_used is not None and _used((keys or [1])[0]) + ROW_CALL_MARGIN > stop_at_used:
            print(f"budget ceiling {stop_at_used} reached; stopping after {len(per)} rows (n is the rows run)")
            break
        if llm is not None and hasattr(llm, "_countered"):  # fresh mock state per scenario
            llm = make_llm(llm_kind, keys)
        per.append(evaluate_row(sid, llm))
        if llm_kind == "live":
            print(f"[{len(per)}/{len(ids)}] {sid} {per[-1].get('final_state') or per[-1].get('error')} "
                  f"used={_used((keys or [1])[0])}", flush=True)
    return assemble(per, es["seed"], llm_kind, f"{shard[0]}/{shard[1]}" if shard else None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42, help="--freeze only")
    ap.add_argument("--freeze", action="store_true", help=f"draw and write {EVAL_SET} once, then exit")
    ap.add_argument("--llm", choices=["none", "mock", "live"], default="none")
    ap.add_argument("--keys", default="", help="live only: comma-separated 1-based key indices, e.g. 1,2,3")
    ap.add_argument("--shard", default="", help="i/k: run rows with index %% k == i-1")
    ap.add_argument("--confirm-live", action="store_true", help="required with --llm live (spends quota)")
    ap.add_argument("--out", default="")
    ap.add_argument("--stop-at-used", type=int, default=None,
                    help="live: stop before a row if the first key's ledger would pass this (e.g. 229+189=418)")
    a = ap.parse_args()
    if a.freeze:
        es = freeze_eval_set(a.n, a.seed)
        print(f"wrote {EVAL_SET}: n={es['n']} strata={es['strata']} excluded={len(es['excluded_ids'])} "
              f"sha256={es['sha256']}")
        return
    if a.llm == "live" and not a.confirm_live:
        raise SystemExit("--llm live spends Gemini quota; it needs the human's approval and --confirm-live")
    shard = tuple(int(x) for x in a.shard.split("/")) if a.shard else None
    keys = [int(x) for x in a.keys.split(",") if x.strip()] or None
    # a mock run is scripted, never "measured" results: it never goes to eval/results.json
    out = a.out or ("runs/eval_mock.json" if a.llm == "mock"
                    else f"eval/results_partial_{shard[0]}of{shard[1]}.json" if shard
                    else load_config()["paths"]["eval_results"])
    res = run(a.n, a.llm, keys, shard, a.stop_at_used)
    with open(repo_path(out), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    s = res["summary"]
    print(f"wrote {out}: n={res['n']} llm={a.llm} errors={s['n_errors']} consensus={s['consensus_rate']} "
          f"by_r2={s['consensus_by_r2']} fallback={s['fallback_rate']} escalate={s['escalate_rate']} "
          f"unsafe_blocked={s['unsafe_proposals_blocked']} unsafe_exec={s['unsafe_plans_executed']} "
          f"J_mean={s['J_mean']} regret_vs_B1={s['regret_vs_B1_mean']}")


if __name__ == "__main__":
    main()
