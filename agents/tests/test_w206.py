"""W2-06-fix: one GeminiClient reused across asyncio.run() calls (eval: one loop per scenario)."""
import asyncio
import json
from types import SimpleNamespace

from core.config import load_config
from agents import killswitch
from agents.client import GeminiClient
from agents.tests.test_client import _calls, _run


class LoopBoundGenai:
    """Like google-genai's aio session: bound to the first loop it runs on."""
    made = 0

    def __init__(self, api_key):
        LoopBoundGenai.made += 1
        self.loop = None
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: self._gen(**kw)))

    async def _gen(self, model, contents, config):   # replaced per test
        raise NotImplementedError


def test_client_survives_a_new_event_loop(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-key")
    monkeypatch.setenv("GEMINI_API_KEY_2", "")
    monkeypatch.setenv("GEMINI_API_KEY_3", "")
    import google.genai
    monkeypatch.setattr(google.genai, "Client", LoopBoundGenai)
    cfg = load_config()
    cfg["llm_budget"]["per_key_rpm_cap"] = 10_000
    killswitch.set_llm_enabled(True)
    calls = _calls()
    # each request answers with a valid position for whichever role the prompt is for
    by_prompt = {c.prompt: {"agent": r, "round": 1, "action": "PROPOSE", "ranking": ["opt_4"],
                            "acceptable": ["opt_4"], "cites": [], "rationale": "ok"} for r, c in calls.items()}

    async def gen(self, model, contents, config):
        loop = asyncio.get_running_loop()
        if self.loop is not None and self.loop is not loop:
            raise RuntimeError("Event loop is closed")
        self.loop = loop
        body = next(v for p, v in by_prompt.items() if contents.startswith(p))
        return SimpleNamespace(text=json.dumps(body), usage_metadata=None)
    monkeypatch.setattr(LoopBoundGenai, "_gen", gen)
    LoopBoundGenai.made = 0
    llm = GeminiClient(cfg)
    first = _run(llm, calls)      # loop 1
    second = _run(llm, calls)     # loop 2: same client object, like eval's asyncio.run per scenario
    assert [m.status for m in first] == ["ok"] * 3
    assert [m.status for m in second] == ["ok"] * 3, [m.errors for m in second]
    assert LoopBoundGenai.made == 2   # rebuilt once for the new loop
