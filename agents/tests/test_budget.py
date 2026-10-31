import asyncio
import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from core.config import load_config
from agents import budget, killswitch
from agents.bundles import load_bundle
from agents.client import GeminiClient, MockLLMClient
from agents.coordinator import Coordinator
from agents.prompting import RoundState, build_call
from agents.tests.fakes import install

PT = ZoneInfo("America/Los_Angeles")
NOON = datetime(2026, 10, 30, 12, 0, tzinfo=PT).timestamp()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-key")
    monkeypatch.setenv("GEMINI_API_KEY_2", "")
    monkeypatch.setenv("GEMINI_API_KEY_3", "")
    c = load_config()
    c["paths"]["runs_dir"] = str(tmp_path)
    c["llm_budget"]["ledger"] = str(tmp_path / "llm_budget.json")
    c["llm_budget"]["used_before_ledger"] = {"GEMINI_API_KEY": 211}
    c["llm_budget"]["per_key_rpm_cap"] = 10_000      # tests that don't test the RPM limiter
    c["rate_limit"]["backoff_initial_s"] = 0
    killswitch.set_llm_enabled(True)
    return c


def test_fresh_ledger_starts_from_dashboard(cfg):
    st = budget.budget_status(cfg, now=NOON)
    assert st.keys["GEMINI_API_KEY"] == {"used_today": 211, "cap": 480, "remaining": 269, "rpm_cap": 10_000}
    assert st.resets_at.startswith("2026-10-31T00:00:00")
    assert "test-not-a-key" not in json.dumps(json.load(open(cfg["llm_budget"]["ledger"])))


def test_concurrent_reserve_never_exceeds_cap(cfg):
    cfg["llm_budget"]["per_key_daily_cap"] = 250            # 39 left
    results = []
    def worker():
        for _ in range(10):
            results.append(budget.reserve("GEMINI_API_KEY", cfg, now=NOON))
    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(results) == 39 and len(results) == 80
    assert budget.budget_status(cfg, now=NOON).keys["GEMINI_API_KEY"]["used_today"] == 250


def test_pacific_midnight_rollover(cfg):
    assert budget.reserve("GEMINI_API_KEY", cfg, now=NOON)
    before = datetime(2026, 10, 30, 23, 59, 30, tzinfo=PT).timestamp()
    after = datetime(2026, 10, 31, 0, 0, 30, tzinfo=PT).timestamp()
    assert budget.budget_status(cfg, now=before).keys["GEMINI_API_KEY"]["used_today"] == 212
    assert budget.budget_status(cfg, now=after).keys["GEMINI_API_KEY"]["used_today"] == 0


def test_rpm_limiter_waits(cfg):
    cfg["llm_budget"]["per_key_rpm_cap"] = 3
    t = [NOON]
    slept = []
    async def fake_sleep(s):
        slept.append(s)
        t[0] += s
    async def go():
        return [await budget.acquire("GEMINI_API_KEY", cfg, clock=lambda: t[0], sleep=fake_sleep) for _ in range(4)]
    res = asyncio.run(go())
    assert all(ok for ok, _, _ in res) and len(slept) == 1 and 59 < slept[0] <= 61   # 4th waited ~60 s


def pilot_call():
    b = load_bundle()
    return build_call(b.scenario, b.options, b.checks, "PILOT",
                      RoundState(round=1, candidates=[o.option_id for o in b.options]))


GOOD = {"agent": "PILOT", "round": 1, "action": "PROPOSE", "ranking": ["opt_4"], "acceptable": ["opt_4"],
        "counter": None, "red_lines": [], "cites": [], "rationale": "ok"}


def ask(llm):
    c = pilot_call()
    return asyncio.run(llm.position("PILOT", c.prompt, c.response_model, 1, call=c))


def test_schema_retry_consumes_budget(cfg):
    llm = GeminiClient(cfg)
    install(llm, [dict(GOOD, ranking=["opt_9"]), GOOD])
    assert ask(llm).status == "ok"
    assert budget.budget_status(cfg).keys["GEMINI_API_KEY"]["used_today"] == 213


def test_cap_reached_is_rate_limited_without_request(cfg):
    budget.set_used("GEMINI_API_KEY", 480, cfg)
    llm = GeminiClient(cfg)
    models = install(llm, [GOOD])
    m = ask(llm)
    assert m.status == "rate_limited" and m.errors == ["daily LLM budget exhausted"]
    assert models.requests == [] and llm.n_calls == 0


def test_cap_reached_mid_run_falls_back_safely(cfg):
    budget.set_used("GEMINI_API_KEY", 476, cfg)      # 4 left: R1 (3 calls) then refusals
    cfg["llm_budget"]["per_key_daily_cap"] = 480
    llm = GeminiClient(cfg)
    llm.budget_remaining = lambda: 99                 # let it start, so the in-run refusal path is tested
    install(llm, [dict(GOOD, agent=r) for r in ("ATC", "PILOT", "GROUND")] + [GOOD] * 10)
    c = Coordinator(load_bundle(), "run_budget_mid", config=cfg, llm=llm)
    async def go():
        return [e async for e in c.run()]
    evs = asyncio.run(go())
    assert budget.budget_status(cfg).keys["GEMINI_API_KEY"]["used_today"] == 480
    assert any(e["type"] == "agent_position" and e["data"]["status"] == "rate_limited" for e in evs)
    fb = [e["data"] for e in evs if e["type"] == "fallback"]
    assert fb and fb[0]["plan"] and c.checks[fb[0]["plan"]["option_id"]].feasible


def test_coordinator_refuses_to_start_below_one_run(cfg):
    budget.set_used("GEMINI_API_KEY", 475, cfg)      # 5 < 9
    llm = GeminiClient(cfg)
    models = install(llm, [GOOD] * 10)
    c = Coordinator(load_bundle(), "run_budget_low", config=cfg, llm=llm)
    async def go():
        return [e async for e in c.run()]
    evs = asyncio.run(go())
    types = [e["type"] for e in evs]
    assert "round_started" not in types and models.requests == []
    err = [e["data"] for e in evs if e["type"] == "error"][0]
    assert "LLM budget exhausted" in err["message"]
    assert [e["data"]["reason"] for e in evs if e["type"] == "fallback"] == ["LLM_ERROR"]


def test_narrator_template_uses_no_calls(cfg):
    assert cfg["models"]["narrator_llm"] is False
    llm = MockLLMClient(config=cfg)
    c = Coordinator(load_bundle(), "run_budget_narr", config=cfg, llm=llm)
    async def go():
        return [e async for e in c.run()]
    evs = asyncio.run(go())
    assert any(e["type"] == "narration" for e in evs) and llm.n_calls == 6
