import json
import os

from core.bundle import build_bundle, build_bundle_from_scenario
from core.chaos import apply_chaos
from core.constraints import check_option
from core.mapdata import map_payload
from core.options import make_option
from core.scenario import build_scenario
from core.types import ChaosEvent, MapPayload, ScenarioBundle

DEV = json.load(open("data/dev_rows.json"))["scenario_ids"]


def test_taxiway_block_moves_fallback_gate():
    b = build_bundle(DEV[0])
    plan = next(o for o in b.options if o.option_id == b.fallback.option_id)
    tw = next(g for g in b.scenario.gates if g.gate_id == plan.gate).taxi_path[0]
    s2 = apply_chaos(b.scenario, ChaosEvent(kind="TAXIWAY_BLOCK", params={"taxiway": tw}))
    assert b.scenario.blocked_taxiways == [] and s2.blocked_taxiways == [tw]
    same = make_option(s2, plan.option_id, plan.eta_shift_min, plan.gate, plan.fp_adjustment)
    rep = check_option(s2, same)
    assert not next(r for r in rep.results if r.constraint_id == "H6_taxiway_reachability").passed
    b2 = build_bundle_from_scenario(s2)
    assert b2.fallback.status == "PLAN"
    new = next(o for o in b2.options if o.option_id == b2.fallback.option_id)
    assert new.gate != plan.gate and tw not in next(g for g in s2.gates if g.gate_id == new.gate).taxi_path


def test_runway_closure_halves_aar():
    s = build_scenario(DEV[1])
    s2 = apply_chaos(s, ChaosEvent(kind="RUNWAY_CLOSURE", params={"aar_factor": 0.5}))
    assert s2.aar_reduced == round(s.aar_reduced * 0.5)
    assert len(s2.chaos_applied) == 1 and s.chaos_applied == []


def test_gate_failure_and_weather_cell():
    s = build_scenario(DEV[0])
    g = s.gates[0].gate_id
    s2 = apply_chaos(s, ChaosEvent(kind="GATE_FAILURE", params={"gate_id": g, "duration_min": 90}))
    assert next(x for x in s2.gates if x.gate_id == g).out_of_service
    s3 = apply_chaos(s, ChaosEvent(kind="WEATHER_CELL", params={"turbulence_add": 0.3, "extra_delay_min": 15}))
    assert s3.base_eta_min == s.base_eta_min + 15
    assert all(s3.turbulence_by_fp[k] >= s.turbulence_by_fp[k] for k in s.turbulence_by_fp)


def test_map_payload():
    s = build_scenario(DEV[0])
    mp = map_payload(s)
    assert mp.focus_airport == s.destination.iata
    assert sum(f.role == "disrupted" for f in mp.flights) == 1
    codes = {a.iata for a in mp.airports}
    assert all(f.origin in codes and f.destination in codes for f in mp.flights)


def test_golden_files_validate():
    d = "tests/golden"
    files = [f for f in os.listdir(d) if f.endswith(".json")] if os.path.isdir(d) else []
    assert len(files) >= 2
    for f in files:
        x = json.load(open(os.path.join(d, f)))
        ScenarioBundle.model_validate(x["bundle"])
        MapPayload.model_validate(x["map"])


def test_golden_files_match_generator():
    """Goldens are replayed by W2 fixture mode / W3 mock / hero recordings, so they must equal what core builds
    today. If this fails after a core change, regenerate: python -m core.cli --export <id> tests/golden/<id>.json"""
    d = "tests/golden"
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            x = json.load(open(os.path.join(d, f)))
            sid = x["bundle"]["scenario"]["scenario_id"]
            assert build_bundle(sid).model_dump(mode="json") == x["bundle"], f"stale golden {f}"
            assert map_payload(build_bundle(sid).scenario).model_dump(mode="json") == x["map"], f"stale map {f}"
