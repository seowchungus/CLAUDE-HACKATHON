import json

import pytest

from core.metrics import compute_metrics
from core.options import counter_allowed_values, generate_options
from core.scenario import build_scenario

DEV = json.load(open("data/dev_rows.json"))["scenario_ids"]


@pytest.fixture(scope="module")
def s():
    return build_scenario(DEV[0])


def test_reproducible():
    for sid in DEV:
        assert build_scenario(sid).model_dump_json() == build_scenario(sid).model_dump_json()


def test_provenance_covers_fields(s):
    skip = {"scenario_id", "seed", "fixture", "provenance"}
    for field in type(s).model_fields:
        if field not in skip:
            assert field in s.provenance, field
    for k in ("aar_reduced", "fuel_at_fix_min", "gates", "turbulence_by_fp", "bank.wake",
              "connections.pax_connecting", "disrupted.wake"):
        assert s.provenance[k] == "synthetic"


def test_hold_costs_more_fuel_than_speed_reduction(s):
    gate = s.gates[0].gate_id
    for shift in (10, 20):
        hold = compute_metrics(s, shift, gate, "hold_10" if shift == 10 else "hold_20")
        speed = compute_metrics(s, shift, gate, "speed_reduction")
        assert hold.extra_fuel_min > speed.extra_fuel_min
        assert hold.fuel_at_landing_min < speed.fuel_at_landing_min


def test_misconnects_non_decreasing():
    for sid in DEV:
        s = build_scenario(sid)
        vals = [compute_metrics(s, sh, s.gates[0].gate_id, "as_filed").misconnected_pax
                for sh in counter_allowed_values(s)["eta_shift_min"]]
        assert vals == sorted(vals)


def test_blocked_taxiway(s):
    g = s.gates[0]
    assert compute_metrics(s, 0, g.gate_id, "as_filed").taxi_path_ok
    blocked = s.model_copy(update={"blocked_taxiways": [g.taxi_path[0]]})
    assert not compute_metrics(blocked, 0, g.gate_id, "as_filed").taxi_path_ok


def test_generate_options_shape():
    for sid in DEV:
        s = build_scenario(sid)
        opts = generate_options(s)
        assert 6 <= len(opts) <= 8
        assert [o.option_id for o in opts] == [f"opt_{i + 1}" for i in range(len(opts))]
        assert len({(o.eta_shift_min, o.gate, o.fp_adjustment) for o in opts}) == len(opts)
