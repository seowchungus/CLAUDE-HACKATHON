import asyncio
import json

import pytest

from core.config import load_config
from agents import killswitch
from agents.bundles import load_bundle
from agents.client import GeminiClient, MockLLMClient
from agents.coordinator import Coordinator
from agents.narrator import record_markdown, template_narration
from agents.prompting import RoundState, build_call
from agents.tests.fakes import FakeAPIError, install


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-key")
    monkeypatch.setenv("GEMINI_API_KEY_2", "")
    monkeypatch.setenv("GEMINI_API_KEY_3", "")
    c = load_config()
    c["paths"]["runs_dir"] = str(tmp_path)
    c["rate_limit"]["backoff_initial_s"] = 0
    c["llm_budget"]["ledger"] = str(tmp_path / "llm_budget.json")
    killswitch.set_llm_enabled(True)
    return c


def pilot_call(round=1):
    b = load_bundle()
    st = RoundState(round=round, candidates=[o.option_id for o in b.options])
    return build_call(b.scenario, b.options, b.checks, "PILOT", st)


GOOD = {"agent": "PILOT", "round": 1, "action": "PROPOSE", "ranking": ["opt_4", "opt_1"],
        "acceptable": ["opt_4", "opt_1"], "counter": None, "red_lines": ["H3_fuel_reserve"],
        "cites": ["opt_4.fuel_at_landing_min"], "rationale": "opt_4 keeps 43.0 min of fuel."}


def ask(llm, c):
    return asyncio.run(llm.position("PILOT", c.prompt, c.response_model, c.round, call=c))


def test_429_fails_fast_without_cascade(cfg):
    llm = GeminiClient(cfg)
    models = install(llm, [FakeAPIError(429, "RESOURCE_EXHAUSTED")] * 10)
    m = ask(llm, pilot_call())
    assert m.status == "rate_limited"
    assert len(models.requests) == cfg["rate_limit"]["max_429_retries"] + 1   # back off once, then stop
    assert {r["model"] for r in models.requests} == {cfg["models"]["PILOT"]}  # no model cascade
    assert llm.n_calls == len(models.requests)


def test_503_fails_fast(cfg):
    llm = GeminiClient(cfg)
    models = install(llm, [FakeAPIError(503, "UNAVAILABLE")] * 10)
    assert ask(llm, pilot_call()).status == "rate_limited" and len(models.requests) == 2


def test_structured_output_request(cfg):
    llm = GeminiClient(cfg)
    models = install(llm, [GOOD])
    m = ask(llm, pilot_call())
    assert m.status == "ok" and m.tokens_in == 100 and llm.n_calls == 1
    assert models.requests[0]["config"].response_json_schema is not None


def test_prompt_only_json_path(cfg):
    cfg["structured_output"] = {cfg["models"]["PILOT"]: False}
    llm = GeminiClient(cfg)
    fenced = "Here you go:\n```json\n" + json.dumps(GOOD) + "\n```"
    models = install(llm, ["not json at all", fenced])
    m = ask(llm, pilot_call())
    assert m.status == "ok" and m.retries == 1 and llm.n_calls == 2
    req = models.requests[0]
    assert req["config"].response_json_schema is None and req["config"].response_mime_type is None
    assert "JSON schema" in req["contents"]
    assert "rejected by the validator" in models.requests[1]["contents"]


def test_second_schema_failure_is_schema_fail(cfg):
    llm = GeminiClient(cfg)
    bad = dict(GOOD, ranking=["opt_9"])
    install(llm, [bad, bad])
    m = ask(llm, pilot_call())
    assert m.status == "schema_fail" and llm.n_calls == 2 and any("opt_9" in e for e in m.errors)


def run(coord):
    async def go():
        return [e async for e in coord.run()]
    return asyncio.run(go())


def test_mock_run_reports_calls_and_narration(cfg):
    llm = MockLLMClient(config=cfg)
    c = Coordinator(load_bundle(), "run_w203_mock", config=cfg, llm=llm)
    evs = run(c)
    ended = evs[-1]["data"]
    assert ended["n_llm_calls"] == llm.n_calls == 6
    assert evs[0]["data"]["scripted"] is True
    narr = [e for e in evs if e["type"] == "narration"]
    assert len(narr) == 1 and len(narr[0]["data"]["text"].split()) <= 120
    assert [e["type"] for e in evs][-3:] == ["narration", "awaiting_approval", "run_ended"]


def test_counter_checked_failed_and_check(cfg):
    c = Coordinator(load_bundle(), "run_w203_cc", config=cfg, llm=MockLLMClient(config=cfg))
    from core.types import AgentRole  # noqa: F401
    from agents.schema import Counter
    run(c)
    bad = c._check_counter(2, "PILOT", Counter(base_option="opt_4", param="gate", value="B2"))
    assert bad["accepted"] is False and bad["check"] is not None and "H4_gate_validity" in bad["failed"]
    dup = c._check_counter(2, "PILOT", Counter(base_option="opt_4", param="gate", value="C1"))
    assert dup["check"] is None and dup["failed"] == [] and "duplicate" in dup["reason"]


def test_hallucinate_rejected_reference(cfg):
    c = Coordinator(load_bundle(), "run_w203_hall", config=cfg, llm=MockLLMClient("hallucinate", config=cfg))
    evs = run(c)
    pilot = [e["data"] for e in evs if e["type"] == "agent_position" and e["data"]["agent"] == "PILOT"][0]
    assert pilot["status"] == "schema_fail" and pilot["position"] is None
    assert "unknown option opt_9" in pilot["errors"] and any("gate_Z9" in e for e in pilot["errors"])


def test_unsafe_ends_in_fallback(cfg):
    c = Coordinator(load_bundle(), "run_w203_unsafe", config=cfg, llm=MockLLMClient("unsafe", config=cfg))
    evs = run(c)
    fb = [e["data"] for e in evs if e["type"] == "fallback"]
    assert fb and fb[0]["plan"] and c.checks[fb[0]["plan"]["option_id"]].feasible
    assert any(e["type"] == "veto" for e in evs)


def test_cancel_superseded(cfg):
    class Slow(MockLLMClient):
        async def position(self, *a, **k):
            await asyncio.sleep(10)

    c = Coordinator(load_bundle(), "run_w203_cancel", config=cfg, llm=Slow(config=cfg))

    async def go():
        evs = []

        async def consume():
            async for e in c.run():
                evs.append(e)
        t = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        assert await c.cancel() is True
        await asyncio.wait_for(t, 2)
        return evs
    evs = asyncio.run(go())
    assert evs[-1]["type"] == "run_ended" and evs[-1]["data"]["final_state"] == "SUPERSEDED"
    assert "consensus" not in [e["type"] for e in evs] and "fallback" not in [e["type"] for e in evs]
    from core.log import verify_chain
    assert verify_chain(c.log.path).ok
    assert asyncio.run(c.cancel()) is False


def test_record_markdown(cfg):
    c = Coordinator(load_bundle(), "run_w203_rec", config=cfg, llm=MockLLMClient(config=cfg))
    evs = run(c)
    md = record_markdown(c.bundle, evs, c.log.head_hash())
    assert md.startswith("# Resolution Record: AA1234") and "SYNTHETIC" in md and c.log.head_hash() in md
    assert "## Constraint checks (plan)" in md and "Veto" in md
    assert template_narration(c.bundle, evs).split()[0] == "AA1234"
