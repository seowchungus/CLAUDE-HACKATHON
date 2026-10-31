"""Batch evaluation (proposal §8, CONTRACTS.md §6). Skeleton: B0 (FCFS) and B1 (optimiser) only, no LLM.

  python -m eval.run_eval [--n 30] [--seed 42] [--out eval/results.json]

Test set: N qualifying rows, stratified by delay type (WEATHER / LATE_AIRCRAFT, alternating) across the
top-6 destination airports by qualifying volume, excluding data/dev_rows.json. Deterministic for a seed.
Every number written is measured; fields that were not run are null (the LLM part plugs in at W1-05).
"""
import argparse
import json
import random
from datetime import datetime, timezone

import polars as pl

from core.bundle import build_bundle
from core.config import load_config, repo_path
from core.scenario import _qualifying, airports, dev_scenario_ids, make_scenario_id

N_AIRPORTS = 6


def select_test_set(n: int, seed: int) -> list[str]:
    q = _qualifying()
    known = list(airports())
    q = q.filter(pl.col("ORIGIN_AIRPORT").is_in(known) & pl.col("DESTINATION_AIRPORT").is_in(known))
    top = (q.group_by("DESTINATION_AIRPORT").len().sort(["len", "DESTINATION_AIRPORT"], descending=[True, False])
           .head(N_AIRPORTS)["DESTINATION_AIRPORT"].to_list())
    rng = random.Random(seed)
    dev = set(dev_scenario_ids())
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
        ap, is_w = top[k % len(top)], (k // len(top)) % 2 == 0
        k += 1
        if pools[(ap, is_w)]:
            out.append(pools[(ap, is_w)].pop())
    return out


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def run(n: int, seed: int) -> dict:
    ids = select_test_set(n, seed)
    per: list[dict] = []
    for sid in ids:
        try:
            b = build_bundle(sid)
        except Exception as e:  # noqa: BLE001 - record and continue; the eval must not die on one row
            per.append({"scenario_id": sid, "error": f"{type(e).__name__}: {e}"})
            continue
        f = b.fallback
        per.append({
            "scenario_id": sid, "final_state": None, "rounds_used": None, "option_id": None, "J": None,
            "J_B0": b.fcfs.metrics.cost_J, "J_B1": f.cost_J, "unsafe_blocked": None, "latency_ms": None,
            "run_id": None,
            "disruption_type": b.scenario.disruption_type, "destination": b.scenario.destination.iata,
            "B0_feasible": b.checks["opt_fcfs"].feasible, "B1_status": f.status, "B1_option_id": f.option_id,
            "n_options": len(b.options), "n_feasible": sum(b.checks[o.option_id].feasible for o in b.options),
        })
    ok = [p for p in per if "error" not in p]
    with open(repo_path("data/status_quo.json")) as fh:
        sq = json.load(fh)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "n": len(ok), "n_dev": len(dev_scenario_ids()), "seed": seed,
        "status_quo": {k: sq[k] for k in ("qualifying_flights", "weather_delay_min", "late_aircraft_delay_min")},
        "summary": {
            "consensus_rate": None, "consensus_by_r2": None, "consensus_by_r3": None,
            "fallback_rate": None,
            "escalate_rate": None,
            "unsafe_proposals_blocked": None, "unsafe_plans_executed": None,
            "schema_failure_rate": None, "retry_rate": None,
            "latency_p50_ms": None, "latency_p95_ms": None, "tokens_per_resolution": None,
            "J_mean": {"accord": None, "B0_fcfs": _mean([p["J_B0"] for p in ok]),
                       "B1_optimizer": _mean([p["J_B1"] for p in ok if p["J_B1"] is not None])},
            "regret_vs_B1_mean": None,
            "vs_B0": {"bank_delay_added_min": None, "misconnected_pax": None, "ramp_overtime_min": None},
            "B1_escalate_rate": round(sum(p["B1_status"] == "ESCALATE" for p in ok) / len(ok), 3) if ok else None,
            "B0_infeasible_rate": round(sum(not p["B0_feasible"] for p in ok) / len(ok), 3) if ok else None,
            "n_errors": len(per) - len(ok),
        },
        "ablations": {"B2_single_agent": None, "B3_model": None},
        "per_scenario": per,
        "measured": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=load_config()["paths"]["eval_results"])
    a = ap.parse_args()
    res = run(a.n, a.seed)
    with open(repo_path(a.out), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    s = res["summary"]
    print(f"wrote {a.out}: n={res['n']} errors={s['n_errors']} J_mean={s['J_mean']} "
          f"B1_escalate={s['B1_escalate_rate']} B0_infeasible={s['B0_infeasible_rate']}")


if __name__ == "__main__":
    main()
