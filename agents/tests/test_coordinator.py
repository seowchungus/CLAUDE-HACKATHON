import asyncio
import json

import pytest

from core.config import load_config, repo_path
from core.log import verify_chain
from agents import killswitch
from agents._compat import load_bundle
from agents.client import MockLLMClient
from agents.coordinator import Coordinator
from agents.schema import AgentMessage


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["paths"]["runs_dir"] = str(tmp_path)
    return c


@pytest.fixture(autouse=True)
def _llm_on():
    killswitch.set_llm_enabled(True)
    yield
    killswitch.set_llm_enabled(True)


def run(coord):
    async def go():
        return [e async for e in coord.run()]
    return asyncio.run(go())


def types_of(evs):
    return [e["type"] for e in evs]


def one(evs, t):
    xs = [e for e in evs if e["type"] == t]
    assert len(xs) == 1, (t, types_of(evs))
    return xs[0]["data"]


def check_invariants(evs, coord):
    ts = types_of(evs)
    assert ts.count("round_started") <= 3
    assert sum(t in ("consensus", "fallback") for t in ts) == 1
    assert [e["seq"] for e in evs] == list(range(len(evs)))
    for e in evs:
        if e["type"] == "counter_checked":
            assert e["data"]["round"] < 3
        if e["type"] == "consensus":
            assert e["data"]["check"]["feasible"]
        if e["type"] == "fallback" and e["data"]["plan"] is not None:
            assert coord.checks[e["data"]["plan"]["option_id"]].feasible
    v = verify_chain(coord.log.path)
    assert v.ok and v.n_entries == len(evs) + 1          # + scenario_loaded at seq 0
    log = [json.loads(l) for l in open(coord.log.path)]
    assert [l["hash"] for l in log[1:]] == [e["log_hash"] for e in evs]
    assert one(evs, "run_ended")["chain_ok"] is True


def test_consensus_path(cfg):
    c = Coordinator(load_bundle(), "run_test_consensus", config=cfg, llm=MockLLMClient(config=cfg))
    evs = run(c)
    check_invariants(evs, c)
    d = one(evs, "consensus")
    assert d["round"] == 2 and set(d["accepts"]) == {"ATC", "PILOT", "GROUND"}
    assert types_of(evs).count("agent_position") == 6
    assert any(e["type"] == "counter_checked" and e["data"]["accepted"] for e in evs)
    assert one(evs, "run_ended")["final_state"] == "CONSENSUS"


def test_shape_matches_fixture(cfg):
    fixture = [json.loads(l) for l in open(repo_path("docs/fixtures/run_events.jsonl"))]
    c = Coordinator(load_bundle(), "run_test_shape", config=cfg, llm=MockLLMClient(config=cfg))
    evs = run(c)
    assert set(evs[0]) == set(fixture[0])                 # envelope keys
    ours = {}
    for e in evs:
        ours.setdefault(e["type"], set(e["data"]))
    for e in fixture:
        if e["type"] in ours:
            assert ours[e["type"]] == set(e["data"]), e["type"]
    optional = {"narration", "veto", "counter_checked"}
    assert {e["type"] for e in fixture} - set(ours) <= optional


def test_deadlock_falls_back_after_round3(cfg):
    c = Coordinator(load_bundle(), "run_test_deadlock", config=cfg, llm=MockLLMClient("deadlock", config=cfg))
    evs = run(c)
    check_invariants(evs, c)
    assert types_of(evs).count("round_started") == 3
    fb = one(evs, "fallback")
    assert fb["reason"] == "NO_CONSENSUS" and fb["plan"] is not None
    assert not any(e["type"] == "counter_checked" and e["data"]["round"] == 3 for e in evs)
    assert one(evs, "run_ended")["final_state"] == "FALLBACK"


def test_killed_falls_back_with_zero_calls(cfg):
    killswitch.set_llm_enabled(False)
    llm = MockLLMClient(config=cfg)
    c = Coordinator(load_bundle(), "run_test_killed", config=cfg, llm=llm)
    evs = run(c)
    check_invariants(evs, c)
    assert one(evs, "fallback")["reason"] == "LLM_KILLED"
    assert one(evs, "run_ended")["n_llm_calls"] == 0 and llm.n_calls == 0
    assert "round_started" not in types_of(evs)


def test_kill_mid_run(cfg):
    class KillAfterR1(MockLLMClient):
        async def position(self, role, prompt, response_model, round, call=None):
            m = await super().position(role, prompt, response_model, round, call=call)
            if round == 1 and role == "GROUND":
                killswitch.set_llm_enabled(False)
            return m
    c = Coordinator(load_bundle(), "run_test_kill_mid", config=cfg, llm=KillAfterR1(config=cfg))
    evs = run(c)
    check_invariants(evs, c)
    assert one(evs, "fallback")["reason"] == "LLM_KILLED"
    assert types_of(evs).count("round_started") == 1


def test_unsafe_agreement_vetoed(cfg):
    c = Coordinator(load_bundle(), "run_test_unsafe", config=cfg, llm=MockLLMClient("unsafe", config=cfg))
    evs = run(c)
    check_invariants(evs, c)
    vetoes = [e["data"] for e in evs if e["type"] == "veto"]
    assert vetoes and set(vetoes[0]["agents"]) == {"ATC", "PILOT", "GROUND"}
    assert "H3_fuel_reserve" in vetoes[0]["failed"]
    final = [e for e in evs if e["type"] in ("consensus", "fallback")][0]["data"]
    assert (final.get("option_id") or final["plan"]["option_id"]) != vetoes[0]["option_id"]


def test_checker_overrides_unanimous_accept(cfg):
    """If the tentative option turns infeasible, a unanimous ACCEPT is vetoed, never a consensus."""
    holder = {}

    class Flip(MockLLMClient):
        async def position(self, role, prompt, response_model, round, call=None):
            coord = holder["c"]
            t = call.ctx.tentative
            if round == 2 and t and coord.checks[t].feasible:
                rep = coord.checks[t]
                res = [r.model_copy(update={"passed": False, "detail": "test: forced fail"})
                       if r.constraint_id == "H3_fuel_reserve" else r for r in rep.results]
                coord.checks[t] = rep.model_copy(update={"feasible": False, "results": res})
            return await super().position(role, prompt, response_model, round, call=call)

    c = Coordinator(load_bundle(), "run_test_override", config=cfg, llm=Flip(config=cfg))
    holder["c"] = c
    evs = run(c)
    assert "consensus" not in types_of(evs)
    assert one(evs, "fallback")["reason"] == "NO_CONSENSUS"
    assert any(e["type"] == "veto" and set(e["data"]["agents"]) == {"ATC", "PILOT", "GROUND"} for e in evs)


def test_schema_fail_counts_as_reject(cfg):
    class PilotBroken(MockLLMClient):
        async def position(self, role, prompt, response_model, round, call=None):
            if role == "PILOT" and round >= 2:
                self.n_calls += 1
                return AgentMessage(agent=role, round=round, status="schema_fail", position=None,
                                    model="mock", latency_ms=1, errors=["unknown option opt_9"])
            return await super().position(role, prompt, response_model, round, call=call)
    c = Coordinator(load_bundle(), "run_test_schemafail", config=cfg, llm=PilotBroken(config=cfg))
    evs = run(c)
    check_invariants(evs, c)
    assert "consensus" not in types_of(evs)
    assert one(evs, "fallback")["reason"] == "NO_CONSENSUS"


def test_approve_closes_chain(cfg):
    c = Coordinator(load_bundle(), "run_test_approve", config=cfg, llm=MockLLMClient(config=cfg))
    evs = run(c)
    oid = one(evs, "awaiting_approval")["option_id"]
    res = asyncio.run(c.approve("APPROVE", oid, by="duty manager"))
    assert res["ok"] and res["final_hash"] == evs[-1]["log_hash"]
    last = json.loads(open(c.log.path).read().splitlines()[-1])
    assert last["event_type"] == "approved" and last["actor"] == "HUMAN"
    assert verify_chain(c.log.path).ok
    bad = asyncio.run(c.approve("OVERRIDE", "opt_5", by="x"))
    assert not bad["ok"]


def test_max_rounds_asserted(cfg):
    cfg["negotiation"]["MAX_ROUNDS"] = 4
    with pytest.raises(AssertionError):
        Coordinator(load_bundle(), "run_test_max", config=cfg, llm=MockLLMClient(config=cfg))
