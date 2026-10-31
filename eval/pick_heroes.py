"""Pick demo hero scenarios (proposal §10 demo insurance) by "tension", under the workbook rules.

  python -m eval.pick_heroes [--per-airport 60] [--top 10] [--export 2]

Scans a seeded sample of qualifying rows at HUBS (dev rows excluded) and scores each bundle:
  +2 misconnected_pax varies across options    +1 >= 2 infeasible options     +2 fallback != FCFS plan
  +1 per extra distinct role favourite (ATC bank delay, PILOT misconnects/fuel, GROUND overtime/gate change)
  +1 a tempting option fails H3 or H4          +1 an option fails the gate-change notice   +1 FCFS is unsafe
Writes eval/hero_candidates.json (top N, with one-line reasons). Heroes are excluded from the eval set
(eval/run_eval.py reads this file). The top --export are written to tests/golden/ as {bundle, map}.
"""
import argparse
import json
import random
from datetime import datetime, timezone

import polars as pl

from core.bundle import build_bundle
from core.cli import export
from core.config import repo_path
from core.constraints import failed_ids
from core.scenario import _qualifying, airports, dev_scenario_ids, make_scenario_id

HUBS = ["ORD", "ATL", "DFW", "DEN", "LAX", "SFO"]


def favourites(b) -> tuple[str, str, str] | None:
    feas = [o for o in b.options if b.checks[o.option_id].feasible]
    if not feas:
        return None
    J = lambda o: o.metrics.cost_J  # noqa: E731
    atc = min(feas, key=lambda o: (o.metrics.bank_delay_added_min, o.metrics.throughput_loss, J(o)))
    pilot = min(feas, key=lambda o: (o.metrics.misconnected_pax, o.metrics.hold_min, o.metrics.extra_fuel_min, J(o)))
    ground = min(feas, key=lambda o: (o.metrics.ramp_overtime_min, o.metrics.gate_change,
                                      -o.metrics.turnaround_buffer_min, J(o)))
    return atc.option_id, pilot.option_id, ground.option_id


def score(sid: str) -> dict | None:
    try:
        b = build_bundle(sid)
    except Exception:  # noqa: BLE001
        return None
    fails = {o.option_id: failed_ids(b.checks[o.option_id]) for o in b.options}
    details = [r.detail for o in b.options for r in b.checks[o.option_id].results if not r.passed]
    mis = [o.metrics.misconnected_pax for o in b.options]
    fav = favourites(b)
    plan = next((o for o in b.options if o.option_id == b.fallback.option_id), None)
    fb_ne_fcfs = plan is None or (plan.eta_shift_min, plan.gate, plan.fp_adjustment) != (0, b.fcfs.gate, "as_filed")
    n_bad = sum(bool(v) for v in fails.values())
    h3h4 = any({"H3_fuel_reserve", "H4_gate_validity"} & set(v) for v in fails.values())
    notice = any("notice" in d for d in details)
    fcfs_unsafe = not b.checks["opt_fcfs"].feasible
    n_fav = len(set(fav)) if fav else 0
    pts = (2 * (max(mis) > min(mis)) + (n_bad >= 2) + 2 * fb_ne_fcfs + max(0, n_fav - 1) + h3h4 + notice
           + fcfs_unsafe)
    if b.fallback.status != "PLAN":
        pts -= 3  # ESCALATE is a failure case, not a hero
    why = [f"misconnects {min(mis)}-{max(mis)}" if max(mis) > min(mis) else "misconnects flat",
           f"{n_bad} infeasible", "fallback != FCFS" if fb_ne_fcfs else "fallback == FCFS",
           f"{n_fav} distinct role favourites"]
    if notice:
        why.append("gate-change notice veto")
    if fcfs_unsafe:
        why.append("FCFS unsafe (" + ",".join(failed_ids(b.checks["opt_fcfs"])) + ")")
    s = b.scenario
    return {"scenario_id": sid, "score": pts, "reason": "; ".join(why),
            "disruption_type": s.disruption_type, "disruption_min": s.disruption_min,
            "destination": s.destination.iata, "fallback_option": b.fallback.option_id,
            "favourites": dict(zip(("ATC", "PILOT", "GROUND"), fav)) if fav else None}


def sample(per_airport: int, seed: int) -> list[str]:
    q = _qualifying()
    known = list(airports())
    q = q.filter(pl.col("ORIGIN_AIRPORT").is_in(known) & pl.col("DESTINATION_AIRPORT").is_in(HUBS)
                 & (pl.col("SCHEDULED_ARRIVAL") >= 900) & (pl.col("SCHEDULED_ARRIVAL") <= 2100))
    rng = random.Random(seed)
    dev = set(dev_scenario_ids())
    out: list[str] = []
    for ap in HUBS:
        rows = q.filter(pl.col("DESTINATION_AIRPORT") == ap).sort(["DATE", "AIRLINE", "FLIGHT_NUMBER"]).select(
            "DATE", "AIRLINE", "FLIGHT_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT").rows()
        ids = [make_scenario_id(*r) for r in rows]
        ids = [i for i in ids if i not in dev]
        out += rng.sample(ids, min(per_airport, len(ids)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-airport", type=int, default=50)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--export", type=int, default=2)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    ids = sample(a.per_airport, a.seed)
    scored = [x for x in (score(i) for i in ids) if x is not None]
    scored.sort(key=lambda x: (-x["score"], x["scenario_id"]))
    top, seen_ap = [], {}
    for x in scored:  # at most 3 per airport so the heroes are varied
        if seen_ap.get(x["destination"], 0) < 3:
            top.append(x)
            seen_ap[x["destination"]] = seen_ap.get(x["destination"], 0) + 1
        if len(top) >= a.top:
            break
    res = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
           "scanned": len(scored), "airports": HUBS, "seed": a.seed, "rules": "workbook (CONTRACTS v1.2)",
           "candidates": top}
    with open(repo_path("eval/hero_candidates.json"), "w") as f:
        json.dump(res, f, indent=1)
    for x in top:
        print(f"{x['score']:>2}  {x['scenario_id']:32} {x['reason']}")
    for x in top[:a.export]:
        export(x["scenario_id"], repo_path(f"tests/golden/{x['scenario_id']}.json"))


if __name__ == "__main__":
    main()
