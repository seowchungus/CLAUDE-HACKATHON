import json

import pytest

from core.constraints import check_option
from core.fallback import fcfs
from core.scenario import build_scenario
from core.types import CONSTRAINT_IDS

DEV = json.load(open("data/dev_rows.json"))["scenario_ids"]


@pytest.fixture(scope="module")
def base():
    s = build_scenario(DEV[0])
    o = fcfs(s)
    assert check_option(s, o).feasible
    return s, o


def _with(o, **metrics):
    return o.model_copy(update={"metrics": o.metrics.model_copy(update=metrics)})


def _result(s, o, cid):
    rep = check_option(s, o)
    assert [r.constraint_id for r in rep.results] == CONSTRAINT_IDS
    return next(r for r in rep.results if r.constraint_id == cid)


def test_all_pass_on_base(base):
    s, o = base
    rep = check_option(s, o)
    assert rep.feasible and len(rep.results) == 7 and all(len(r.detail) <= 120 for r in rep.results)


def test_h1(base):
    s, o = base
    assert _result(s, _with(o, separation_margin_s=0), "H1_wake_separation").passed
    assert not _result(s, _with(o, separation_margin_s=-5), "H1_wake_separation").passed


def test_h2(base):
    s, o = base
    assert _result(s, _with(o, arrivals_this_hour=s.aar_reduced), "H2_runway_capacity").passed
    assert not _result(s, _with(o, arrivals_this_hour=s.aar_reduced + 1), "H2_runway_capacity").passed


def test_h3(base):
    s, o = base
    assert _result(s, _with(o, fuel_at_landing_min=30.0), "H3_fuel_reserve").passed
    r = _result(s, _with(o, fuel_at_landing_min=27.5), "H3_fuel_reserve")
    assert not r.passed and r.value == 27.5 and r.threshold == 30


def test_h4(base):
    s, o = base
    assert _result(s, o, "H4_gate_validity").passed
    gates = [g.model_copy(update={"out_of_service": True}) if g.gate_id == o.gate else g for g in s.gates]
    assert not _result(s.model_copy(update={"gates": gates}), o, "H4_gate_validity").passed
    busy = _with(o, gate_free_from_min=o.metrics.eta_new_min + 100)
    assert not _result(s, busy, "H4_gate_validity").passed
    small = [g.model_copy(update={"size": "S"}) if g.gate_id == o.gate else g for g in s.gates]
    big = s.model_copy(update={"gates": small, "aircraft_size": "L"})
    assert not _result(big, o, "H4_gate_validity").passed


def test_h5(base):
    s, o = base
    assert _result(s, _with(o, ramp_overtime_min=500), "H5_crew_duty").passed  # overtime is a cost, not H5
    tired = s.model_copy(update={"flight_crew_duty_remaining_min": 5})
    assert not _result(tired, _with(o, eta_new_min=s.base_eta_min + 10), "H5_crew_duty").passed


def test_h6(base):
    s, o = base
    assert _result(s, o, "H6_taxiway_reachability").passed
    assert not _result(s, _with(o, taxi_path_ok=False), "H6_taxiway_reachability").passed


def test_h7(base):
    s, o = base
    assert _result(s, _with(o, turbulence_idx=0.69), "H7_severe_turbulence").passed
    assert not _result(s, _with(o, turbulence_idx=0.7), "H7_severe_turbulence").passed
