import asyncio

import pytest

from core.config import load_config
from agents import killswitch
from agents.bundles import load_bundle
from agents.client import MockLLMClient
from agents.coordinator import Coordinator
from agents.prompting import RoundState, render_prompt


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["paths"]["runs_dir"] = str(tmp_path)
    killswitch.set_llm_enabled(True)
    return c


def finished(cfg, mode="normal", name="run_rf"):
    c = Coordinator(load_bundle(), name, config=cfg, llm=MockLLMClient(mode, config=cfg))
    async def go():
        return [e async for e in c.run()]
    asyncio.run(go())
    return c


def test_max_rounds_explicit_raise(cfg):
    for bad in (0, 4):
        cfg["negotiation"]["MAX_ROUNDS"] = bad
        with pytest.raises(ValueError):
            Coordinator(load_bundle(), "run_rf_max", config=cfg, llm=MockLLMClient(config=cfg))


def test_approve_rules(cfg):
    c = finished(cfg)
    decided = c.decision["option_id"]
    other = next(o.option_id for o in c.options if o.option_id != decided and c.checks[o.option_id].feasible)
    assert asyncio.run(c.approve("APPROVE", other, by="dm"))["code"] == 400      # APPROVE only the decision
    assert asyncio.run(c.approve("OVERRIDE", "opt_5", by="dm"))["ok"] is False  # infeasible never
    r = asyncio.run(c.approve("APPROVE", decided, by="dm"))
    assert r["ok"] and r["final_hash"]
    again = asyncio.run(c.approve("OVERRIDE", other, by="dm"))
    assert again["ok"] is False and again["code"] == 409                       # one approval per run


def test_approve_before_finish_is_409(cfg):
    c = Coordinator(load_bundle(), "run_rf_early", config=cfg, llm=MockLLMClient(config=cfg))
    assert asyncio.run(c.approve("APPROVE", "opt_4", by="dm"))["code"] == 409


def test_escalate_allows_only_override(cfg):
    c = finished(cfg, name="run_rf_esc")
    c.decision = {"source": "ESCALATE", "option_id": None}   # simulate an ESCALATE outcome
    assert asyncio.run(c.approve("APPROVE", None, by="dm"))["ok"] is False
    assert asyncio.run(c.approve("OVERRIDE", None, by="dm"))["ok"] is False   # explicit option required
    assert asyncio.run(c.approve("OVERRIDE", "opt_4", by="dm"))["ok"] is True


def test_block_d_provenance_from_scenario(cfg):
    b = load_bundle()
    s = b.scenario.model_copy(deep=True)
    s.provenance = dict(s.provenance, aar_nominal="synthetic", fuel_at_fix_min="estimated", gates="real")
    st = RoundState(round=1, candidates=[o.option_id for o in b.options])
    atc = render_prompt(s, b.options, b.checks, "ATC", st, cfg)
    assert f"nominal AAR {s.aar_nominal}/h (SYNTHETIC)" in atc and "REAL_DERIVED" not in atc
    pilot = render_prompt(s, b.options, b.checks, "PILOT", st, cfg)
    assert f"{s.fuel_at_fix_min} min (ESTIMATED)" in pilot
    ground = render_prompt(s, b.options, b.checks, "GROUND", st, cfg)
    assert "Gates (REAL):" in ground
