import json
import subprocess
import sys

from core.bundle import build_bundle
from core.constraints import check_all
from core.fallback import solve

DEV = json.load(open("data/dev_rows.json"))["scenario_ids"]


def test_fallback_never_infeasible_and_each_row_has_both():
    for sid in DEV:
        b = build_bundle(sid)
        feas = [c.feasible for k, c in b.checks.items() if k != "opt_fcfs"]
        assert any(feas) and not all(feas), sid
        assert b.fallback.status == "PLAN"
        assert b.checks[b.fallback.option_id].feasible
        js = [j for _, j in b.fallback.ranking]
        assert js == sorted(js)
        assert "opt_fcfs" in b.checks and b.fcfs.option_id == "opt_fcfs"


def test_all_infeasible_escalates():
    b = build_bundle(DEV[0])
    s = b.scenario.model_copy(update={"fuel_at_fix_min": 10.0})
    opts = [o.model_copy(update={"metrics": o.metrics.model_copy(update={"fuel_at_landing_min": 1.0})})
            for o in b.options]
    res = solve(s, opts, check_all(s, opts))
    assert res.status == "ESCALATE" and res.option_id is None and res.cost_J is None
    assert "diversion" in res.reason


def test_fallback_runs_without_agents():
    code = ("import sys, json; sys.modules['agents'] = None\n"
            "from core.bundle import build_bundle\n"
            f"b = build_bundle({DEV[0]!r}); assert b.fallback.status == 'PLAN'\n"
            "assert not any(m.startswith('agents') for m in sys.modules if sys.modules[m] is not None)")
    subprocess.run([sys.executable, "-c", code], check=True)


def test_b1_never_worse_than_feasible_fcfs():
    """FCFS (+0, as filed) is a grid point, so a feasible FCFS can never beat B1. These ATL 2015-12-30 rows did
    before the generator kept the cheapest gate per (shift, fp) (gates differ by ramp wait)."""
    for sid in DEV + ["2015-12-30_WN289_MSP-ATL", "2015-12-30_OO4748_FWA-ATL", "2015-12-30_DL1966_DFW-ATL",
                      "2015-12-30_DL805_PHL-ATL", "2015-12-30_EV5010_ORF-ATL"]:
        b = build_bundle(sid)
        if b.checks["opt_fcfs"].feasible:
            assert b.fallback.status == "PLAN" and b.fallback.cost_J <= b.fcfs.metrics.cost_J, sid
