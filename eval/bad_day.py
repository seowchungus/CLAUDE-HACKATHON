"""Bad-day replay without the LLM (proposal §7.8, W1-07 §3). 0 LLM calls.

  python -m eval.bad_day [--airport ATL --date 2015-12-30] [--workers 8]

Picks the destination airport and date with the most qualifying arrivals in the provided data (unless given),
builds a bundle for every qualifying arrival there that day and sums B0 (FCFS) and B1 (optimiser) outcomes.
Each flight is replayed on its own (no interaction between the day's flights beyond each scenario's own bank).
Writes eval/bad_day.json; eval/run_eval.py copies it into eval/results.json under `bad_day`.
Deterministic baselines only; the LLM negotiation is evaluated on the N=30 set (eval/eval_set.json).
"""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import polars as pl

from core.config import repo_path
from core.scenario import _qualifying, make_scenario_id

OUT = "eval/bad_day.json"
KEYS = ("bank_delay_added_min", "misconnected_pax", "ramp_overtime_min", "cost_J")
LABEL = "deterministic baselines only; the LLM negotiation is evaluated on the N=30 set"


def busiest_day() -> tuple[str, str, int]:
    g = (_qualifying().group_by(["DESTINATION_AIRPORT", "DATE"]).len()
         .sort(["len", "DESTINATION_AIRPORT", "DATE"], descending=[True, False, False]).row(0))
    return g[0], g[1], int(g[2])


def day_ids(airport: str, date: str) -> list[str]:
    q = (_qualifying().filter((pl.col("DESTINATION_AIRPORT") == airport) & (pl.col("DATE") == date))
         .sort(["SCHEDULED_ARRIVAL", "AIRLINE", "FLIGHT_NUMBER"]))
    return [make_scenario_id(*r) for r in q.select(
        "DATE", "AIRLINE", "FLIGHT_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT").rows()]


def replay(sid: str) -> dict:
    from core.bundle import build_bundle
    try:
        b = build_bundle(sid)
    except Exception as e:  # noqa: BLE001 - e.g. origin without coordinates; counted, never guessed
        return {"scenario_id": sid, "error": f"{type(e).__name__}: {e}"}
    plan = next((o for o in b.options if o.option_id == b.fallback.option_id), None)
    return {"scenario_id": sid, "b0_feasible": b.checks["opt_fcfs"].feasible, "b1_status": b.fallback.status,
            "B0": {k: getattr(b.fcfs.metrics, k) for k in KEYS},
            "B1": {k: getattr(plan.metrics, k) for k in KEYS} if plan else None}


def _totals(ms: list[dict]) -> dict:
    t = {k: round(sum(m[k] for m in ms), 2) for k in KEYS}
    t["J"] = t.pop("cost_J")
    t["n_flights"] = len(ms)
    return t


def run(airport: str | None = None, date: str | None = None, workers: int = 8) -> dict:
    if not (airport and date):
        airport, date, _ = busiest_day()
    ids = day_ids(airport, date)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(replay, ids, chunksize=8))
    ok = [r for r in rows if "error" not in r]
    planned = [r for r in ok if r["B1"] is not None]
    return {
        "label": LABEL,
        "airport": airport, "date": date, "n_flights": len(ok),
        "choice": "destination and date with the most qualifying arrivals in the provided data" if airport else "",
        "n_skipped": len(rows) - len(ok),
        "skipped": [{"scenario_id": r["scenario_id"], "error": r["error"]} for r in rows if "error" in r],
        "B0": _totals([r["B0"] for r in ok]),
        "B1": _totals([r["B1"] for r in planned]),
        "B0_on_B1_planned": _totals([r["B0"] for r in planned]),
        "b0_infeasible": sum(not r["b0_feasible"] for r in ok),
        "b1_escalate": sum(r["b1_status"] == "ESCALATE" for r in ok),
        "notes": ("each arrival replayed independently with its own seeded synthetic scenario; B0 totals include "
                  "FCFS plans that break a hard rule (b0_infeasible); B1 totals cover PLAN rows only, so compare "
                  "B1 with B0_on_B1_planned"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--airport")
    ap.add_argument("--date")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    t = time.time()
    res = run(a.airport, a.date, a.workers)
    if a.airport and a.date:
        res["choice"] = "given on the command line"
    with open(repo_path(OUT), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(f"BAD DAY {res['airport']} {res['date']}: {res['n_flights']} qualifying arrivals "
          f"({res['n_skipped']} skipped, no coordinates)  [{LABEL}]")
    print(f"{'':22}{'flights':>8}{'bank_delay':>12}{'misconn_pax':>12}{'ramp_OT':>9}{'J':>11}")
    for k in ("B0", "B0_on_B1_planned", "B1"):
        x = res[k]
        print(f"{k:22}{x['n_flights']:>8}{x['bank_delay_added_min']:>12}{x['misconnected_pax']:>12}"
              f"{x['ramp_overtime_min']:>9}{x['J']:>11}")
    print(f"B0 (FCFS) infeasible: {res['b0_infeasible']}   B1 ESCALATE: {res['b1_escalate']}   "
          f"wrote {OUT} in {time.time() - t:.1f} s")


if __name__ == "__main__":
    main()
