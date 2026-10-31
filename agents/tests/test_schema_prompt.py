import pytest

from agents._compat import counter_allowed_values, load_bundle
from agents.prompting import ROLE_SPLIT_MARKER, ROLES, RoundState, build_call, render_prompt
from agents.schema import ValidationCtx, build_position_model, metric_refs_for, validate_position


@pytest.fixture(scope="module")
def bundle():
    return load_bundle()


def _ctx(b, round=1, **kw):
    ids = [o.option_id for o in b.options]
    return ValidationCtx(agent="PILOT", round=round, candidates=ids, option_ids=ids,
                         metric_refs=metric_refs_for(ids), allowed_values=counter_allowed_values(b.scenario),
                         tentative="opt_4", **kw)


def _raw(round=1, action="PROPOSE", **kw):
    d = {"agent": "PILOT", "round": round, "action": action, "ranking": ["opt_4", "opt_1"],
         "acceptable": ["opt_4", "opt_1"], "counter": None, "red_lines": ["H3_fuel_reserve"],
         "cites": ["opt_4.fuel_at_landing_min"], "rationale": "opt_4 keeps fuel at 43.0 min."}
    d.update(kw)
    return d


@pytest.mark.parametrize("round", [1, 2, 3])
def test_shared_prefix_identical_across_roles(bundle, round):
    st = RoundState(round=round, candidates=[o.option_id for o in bundle.options],
                    tentative="opt_4" if round > 1 else None)
    prompts = {r: render_prompt(bundle.scenario, bundle.options, bundle.checks, r, st) for r in ROLES}
    prefixes = {r: p.split(ROLE_SPLIT_MARKER)[0] for r, p in prompts.items()}
    assert len(set(prefixes.values())) == 1
    assert len(prefixes["ATC"]) > 2000
    assert len(set(prompts.values())) == 3          # blocks C–E differ
    assert "connecting pax" in prompts["PILOT"] and "connecting pax" not in prompts["GROUND"]
    assert "Ramp crew shift" in prompts["GROUND"] and "Ramp crew shift" not in prompts["ATC"]


def test_valid_position_passes(bundle):
    pos, errs = validate_position(_raw(), _ctx(bundle))
    assert errs == [] and pos.ranking[0] == "opt_4"


def test_unknown_option_rejected(bundle):
    pos, errs = validate_position(_raw(ranking=["opt_9", "opt_4"]), _ctx(bundle))
    assert pos is None and any("unknown option opt_9" in e for e in errs)


def test_unknown_metric_ref_rejected(bundle):
    pos, errs = validate_position(_raw(cites=["opt_4.gate_Z9"]), _ctx(bundle))
    assert pos is None and any("unknown metric ref" in e for e in errs)


def test_counter_in_round3_rejected(bundle):
    c = {"base_option": "opt_4", "param": "gate", "value": "A3"}
    pos, errs = validate_position(_raw(round=3, action="ACCEPT", counter=c), _ctx(bundle, round=3))
    assert pos is None and any("not allowed in round 3" in e for e in errs)


def test_counter_action_rejected_in_round3(bundle):
    c = {"base_option": "opt_4", "param": "gate", "value": "A3"}
    pos, errs = validate_position(_raw(round=3, action="COUNTER", counter=c), _ctx(bundle, round=3))
    assert pos is None


@pytest.mark.parametrize("param,value", [("eta_shift_min", 7), ("gate", "Z9"), ("fp_adjustment", "hold_99")])
def test_off_grid_counter_rejected(bundle, param, value):
    c = {"base_option": "opt_4", "param": param, "value": value}
    pos, errs = validate_position(_raw(action="COUNTER", counter=c), _ctx(bundle))
    assert pos is None and any("off-grid" in e for e in errs)


def test_on_grid_counter_coerced(bundle):
    c = {"base_option": "opt_4", "param": "eta_shift_min", "value": "15"}
    pos, errs = validate_position(_raw(action="COUNTER", counter=c), _ctx(bundle))
    assert errs == [] and pos.counter.value == 15


def test_round_action_rules(bundle):
    pos, errs = validate_position(_raw(round=2, action="PROPOSE"), _ctx(bundle, round=2))
    assert pos is None


def test_response_model_enums(bundle):
    ids = [o.option_id for o in bundle.options]
    m1 = build_position_model(ids, metric_refs_for(ids), 1, agent="ATC")
    m3 = build_position_model(ids, metric_refs_for(ids), 3, agent="ATC")
    s1, s3 = m1.model_json_schema(), m3.model_json_schema()
    assert "counter" in s1["properties"] and "counter" not in s3["properties"]
    assert set(s3["properties"]["action"]["enum"]) == {"ACCEPT", "REJECT"}
    assert "opt_9" not in str(s1) and "opt_6" in str(s1)


def test_build_call_has_model_and_ctx(bundle):
    st = RoundState(round=1, candidates=[o.option_id for o in bundle.options])
    c = build_call(bundle.scenario, bundle.options, bundle.checks, "GROUND", st)
    assert c.ctx.agent == "GROUND" and c.prompt.endswith('round = 1.\n')
