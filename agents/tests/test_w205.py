"""W2-05: grounding check (AgentPosition rationale numbers vs cited metrics) and per-run call counts."""
import asyncio

import pytest

from core.config import load_config
from agents import killswitch
from agents.bundles import load_bundle
from agents.client import MockLLMClient
from agents.coordinator import Coordinator
from agents.schema import rationale_numbers, ungrounded_numbers


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["paths"]["runs_dir"] = str(tmp_path)
    killswitch.set_llm_enabled(True)
    return c


@pytest.fixture
def opts():
    return {o.option_id: o for o in load_bundle().options}   # opt_4: fuel 43.0, bank delay 5, eta 1050


def test_grounded(opts):
    assert ungrounded_numbers("opt_4 keeps 43 min fuel and adds 5 min bank delay; ETA 17:30, +5 shift.",
                              ["opt_4.fuel_at_landing_min", "opt_4.bank_delay_added_min",
                               "opt_4.eta_new_min"], opts) == []


def test_ungrounded(opts):
    assert ungrounded_numbers("opt_4 keeps 47 min of fuel.", ["opt_4.fuel_at_landing_min"], opts) == ["47"]
    assert ungrounded_numbers("fuel 43.2 min", ["opt_4.fuel_at_landing_min"], opts) == ["43.2"]


def test_no_numbers(opts):
    assert ungrounded_numbers("opt_4 passes H3 and H1; gate C1 in round 2 is fine (R2).", [], opts) == []


def test_number_of_uncited_metric_is_ungrounded(opts):
    # 43 is opt_4.fuel_at_landing_min, but only bank delay is cited
    assert ungrounded_numbers("opt_4: 43 min fuel.", ["opt_4.bank_delay_added_min"], opts) == ["43"]


def test_rounding_to_written_precision(opts):
    # opt_2 fuel 41.5: "41.5" and "42" (rounded) are grounded, "41" is not
    refs = ["opt_2.fuel_at_landing_min"]
    assert ungrounded_numbers("41.5 or about 42 min", refs, opts) == []
    assert ungrounded_numbers("41 min", refs, opts) == ["41"]


def test_identifiers_are_not_numbers():
    assert rationale_numbers("opt_3 opt_c12 H7_severe_turbulence gate B2 Z9 R3 Round 3") == []
    assert [t for t, _, _ in rationale_numbers("1,200 kg at 17:25, -5 min")] == ["1,200", "17:25", "5"]


def test_hallucinate_flags_one_ungrounded_position(cfg):
    async def go():
        return [e async for e in Coordinator(load_bundle(), "run_h", cfg, llm=MockLLMClient("hallucinate", cfg)).run()]
    pos = [e["data"] for e in asyncio.run(go()) if e["type"] == "agent_position"]
    flagged = [(p["agent"], p["round"]) for p in pos if p["ungrounded"]]
    assert flagged == [("ATC", 1)]
    assert all(p["status"] == "ok" for p in pos if p["ungrounded"])   # a flag, never a rejection


def test_n_llm_calls_per_run_with_shared_client(cfg):
    """Chaos child + parent share one client: each run counts only its own requests."""
    llm = MockLLMClient("normal", cfg)
    deadlock = MockLLMClient("deadlock", cfg)

    async def go(co):
        return [e async for e in co.run()]

    async def both():
        a = Coordinator(load_bundle(), "run_a", cfg, llm=llm)
        b = Coordinator(load_bundle(), "run_b", cfg, llm=llm)
        return await asyncio.gather(go(a), go(b))
    ea, eb = asyncio.run(both())
    ended = [next(e["data"] for e in ev if e["type"] == "run_ended") for ev in (ea, eb)]
    n_pos = [sum(e["type"] == "agent_position" for e in ev) for ev in (ea, eb)]
    assert [x["n_llm_calls"] for x in ended] == n_pos == [6, 6]
    assert llm.n_calls == 12

    # unequal runs interleaved: 9 (deadlock, 3 rounds) and 6 (consensus R2) on one client
    shared = MockLLMClient("normal", cfg)

    async def mixed():
        a = Coordinator(load_bundle(), "run_c", cfg, llm=shared)
        b = Coordinator(load_bundle(), "run_d", cfg, llm=deadlock)
        c = Coordinator(load_bundle(), "run_e", cfg, llm=shared)
        return await asyncio.gather(go(a), go(b), go(c))
    res = asyncio.run(mixed())
    counts = [next(e["data"]["n_llm_calls"] for e in ev if e["type"] == "run_ended") for ev in res]
    assert counts == [6, 9, 6] and shared.n_calls == 12 and deadlock.n_calls == 9
