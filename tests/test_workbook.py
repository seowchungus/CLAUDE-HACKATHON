"""One test per organisers' workbook rule (data/raw/challenge2_operational_constraints.xlsx)."""
import json

import pytest

from core.config import load_config
from core.constraints import check_option
from core.fallback import fcfs
from core.metrics import compute_metrics
from core.options import make_option
from core.scenario import airport_limits, build_scenario
from core.types import FlightRef

DEV = json.load(open("data/dev_rows.json"))["scenario_ids"]
ORD_ROW = "2015-02-26_UA1575_DEN-ORD"


def _res(s, o, cid):
    return next(r for r in check_option(s, o).results if r.constraint_id == cid)


@pytest.fixture(scope="module")
def s():
    return build_scenario(ORD_ROW)


def test_wake_heavy_leader_120s(s):
    th = load_config()["thresholds"]["wake_separation_s"]
    assert th["H-M"] == th["H-H"] == th["H-L"] == 120 and th["M-M"] == 60
    t = s.base_eta_min + 30  # a quiet spot: put one Heavy 1 min ahead of us, nothing else near
    heavy = FlightRef(flight_id="XX1", airline="XX", flight_number=1, tail_number=None, origin="DEN",
                      destination="ORD", sched_dep_min=t - 120, sched_arr_min=t - 1, est_arr_min=t - 1,
                      role="bank", wake="H")
    one = s.model_copy(update={"bank": [heavy], "aar_reduced": 60,
                               "disrupted": s.disrupted.model_copy(update={"wake": "M"})})
    m = compute_metrics(one, 30, s.planned_gate, "as_filed")
    assert m.separation_margin_s == 60 - 120  # 60 s gap behind a Heavy, 120 s required
    o = make_option(one, "o", 30, s.planned_gate, "as_filed")
    assert not _res(one, o, "H1_wake_separation").passed
    light = one.model_copy(update={"bank": [heavy.model_copy(update={"wake": "M"})]})
    assert compute_metrics(light, 30, s.planned_gate, "as_filed").separation_margin_s == 0


def test_spare_fuel_45_and_15_min_holding_limit(s):
    gate = fcfs(s).gate
    assert compute_metrics(s, 0, gate, "as_filed").fuel_at_landing_min == 45.0
    assert _res(s, make_option(s, "o", 15, gate, "as_filed"), "H3_fuel_reserve").passed  # 15 min: exactly 30 left
    assert not _res(s, make_option(s, "o", 20, gate, "hold_20"), "H3_fuel_reserve").passed
    assert "(workbook)" in _res(s, make_option(s, "o", 20, gate, "hold_20"), "H3_fuel_reserve").detail


def test_gate_change_notice_19_fails_20_passes(s):
    spare = next(g for g in s.gates if g.gate_id != s.planned_gate and not g.occupied
                 and {"S": 0, "M": 1, "L": 2}[g.size] >= {"S": 0, "M": 1, "L": 2}[s.aircraft_size])
    for notice, ok in ((19, False), (20, True)):
        sc = s.model_copy(update={"decision_time_min": s.base_eta_min - notice})
        o = make_option(sc, "o", 0, spare.gate_id, "as_filed")
        assert o.metrics.gate_change and o.metrics.gate_change_notice_min == notice
        r = _res(sc, o, "H4_gate_validity")
        assert r.passed is ok, r.detail


def test_13h_duty():
    assert load_config()["thresholds"]["flight_crew_max_duty_min"] == 780
    s = build_scenario(DEV[0])
    assert 0 <= s.flight_crew_duty_remaining_min <= 780 - 60
    o = make_option(s, "o", 10, fcfs(s).gate, "speed_reduction")
    tired = s.model_copy(update={"flight_crew_duty_remaining_min": 9})
    assert not _res(tired, o, "H5_crew_duty").passed
    assert _res(s.model_copy(update={"flight_crew_duty_remaining_min": 10}), o, "H5_crew_duty").passed


def test_only_spare_gates_free_at_eta():
    for sid in DEV:
        s = build_scenario(sid)
        t = s.base_eta_min + int(s.row.taxi_in or 8)
        free = [g for g in s.gates if not any(a <= t < b for a, b in g.occupied)]
        assert len(free) == s.airport_limits["spare_gates_at_any_time"] in (2, 3), sid


def test_ord_aar_nominal_45(s):
    assert s.airport_limits == airport_limits("ORD")
    assert airport_limits("ORD")["max_runway_ops_per_hour"] == 90 and s.aar_nominal == 45
    assert s.provenance["aar_nominal"] == "synthetic" and s.provenance["airport_limits"] == "synthetic"
    assert airport_limits("ZZZ")["size_class"] == load_config()["workbook"]["default_size_class"]
