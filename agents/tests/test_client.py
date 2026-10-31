import asyncio

from agents import killswitch
from agents.bundles import load_bundle
from agents.client import MockLLMClient
from agents.prompting import ROLES, RoundState, build_call


def _calls(round=1):
    b = load_bundle()
    st = RoundState(round=round, candidates=[o.option_id for o in b.options],
                    tentative="opt_4" if round > 1 else None)
    return {r: build_call(b.scenario, b.options, b.checks, r, st) for r in ROLES}


def _run(llm, calls):
    async def go():
        return await asyncio.gather(*(llm.position(r, c.prompt, c.response_model, c.round, call=c)
                                      for r, c in calls.items()))
    return asyncio.run(go())


def test_mock_round1_three_valid_positions():
    llm = MockLLMClient()
    msgs = _run(llm, _calls())
    assert [m.status for m in msgs] == ["ok"] * 3 and llm.n_calls == 3
    assert msgs[2].position.counter is not None and msgs[2].position.counter.param == "gate"


def test_mock_respects_killswitch():
    killswitch.set_llm_enabled(False)
    try:
        llm = MockLLMClient()
        msgs = _run(llm, _calls())
        assert [m.status for m in msgs] == ["killed"] * 3 and llm.n_calls == 0
    finally:
        killswitch.set_llm_enabled(True)


def test_gemini_client_killed_without_network(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-key")
    from agents.client import GeminiClient
    llm = GeminiClient()
    killswitch.set_llm_enabled(False)
    try:
        msgs = _run(llm, _calls())
        assert all(m.status == "killed" for m in msgs) and llm.n_calls == 0
    finally:
        killswitch.set_llm_enabled(True)
