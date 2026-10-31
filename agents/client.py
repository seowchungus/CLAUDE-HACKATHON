"""LLM clients. One call = one agent. GeminiClient (live) and MockLLMClient (offline, deterministic).

Neither client computes numbers or checks legality: Gemini ranks the pre-computed table; the mock
ranks by sorting existing metrics. All validation happens in agents.schema.validate_position.
"""
import asyncio
import json
import os
import random
import time
from typing import Callable, Protocol

from dotenv import dotenv_values

from core.config import load_config, repo_path
from agents import killswitch
from agents.prompting import AgentCall
from agents.schema import AgentMessage, AgentPosition, Counter, validate_position


class LLMClient(Protocol):
    async def position(self, role: str, prompt: str, response_model: type, round: int,
                       call: AgentCall | None = None) -> AgentMessage: ...


def _api_keys() -> list[str]:
    """GEMINI_API_KEY, _2, _3 from .env (process env overrides). Never logged."""
    file_vals = dotenv_values(repo_path(".env")) if os.path.exists(repo_path(".env")) else {}
    keys = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"):
        v = os.environ.get(name) or file_vals.get(name)
        if v and v.strip() and "your" not in v.lower():
            keys.append(v.strip())
    return keys


def _is_429(e: Exception) -> bool:
    return getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e)[:300]


def _is_transient(e: Exception) -> bool:
    """429 rate limit or 503 overload: back off, then switch to models.backup."""
    return _is_429(e) or getattr(e, "code", None) in (500, 503) or "UNAVAILABLE" in str(e)[:300]


class GeminiClient:
    """google-genai async client. JSON-schema output, per-call timeout, 1 schema retry, 429 back-off,
    switch to models.backup after max_429_retries. Each role uses its own key when several exist."""

    ROLE_KEY_INDEX = {"ATC": 0, "PILOT": 1, "GROUND": 2, "NARRATOR": 0}
    THINKING_LEVEL = "low"   # ranking a precomputed table needs little reasoning; keeps latency < timeout

    def __init__(self, config: dict | None = None):
        from google import genai
        self._genai = genai
        self.cfg = config or load_config()
        self.keys = _api_keys()
        if not self.keys:
            raise RuntimeError("GEMINI_API_KEY missing in .env")
        self._clients = [genai.Client(api_key=k) for k in self.keys]
        self.n_calls = 0
        self._no_thinking: set[str] = set()   # models that reject thinking_config

    def model_for(self, role: str) -> str:
        return self.cfg["models"][role]

    def _client(self, role: str, bump: int = 0):
        return self._clients[(self.ROLE_KEY_INDEX.get(role, 0) + bump) % len(self._clients)]

    async def _generate(self, role: str, model: str, prompt: str, schema: dict | None, key_bump: int):
        from google.genai import types
        neg = self.cfg["negotiation"]
        kw = dict(temperature=neg["temperature"])
        if schema is not None:
            kw.update(response_mime_type="application/json", response_json_schema=schema)
        if model not in self._no_thinking:
            kw["thinking_config"] = types.ThinkingConfig(thinking_level=self.THINKING_LEVEL)
        try:
            return await asyncio.wait_for(
                self._client(role, key_bump).aio.models.generate_content(
                    model=model, contents=prompt, config=types.GenerateContentConfig(**kw)),
                timeout=neg["call_timeout_s"])
        except Exception as e:  # noqa: BLE001
            if getattr(e, "code", None) == 400 and "hinking" in str(e) and model not in self._no_thinking:
                self._no_thinking.add(model)
                return await self._generate(role, model, prompt, schema, key_bump)
            raise

    async def _generate_with_backoff(self, role: str, prompt: str, schema: dict | None):
        """Returns (resp, model_used). 429/503: exponential back-off, then models.backup after
        max_429_retries. A timeout on the primary model goes straight to the backup (one attempt)."""
        rl = self.cfg["rate_limit"]
        model = self.model_for(role)
        backup = self.cfg["models"]["backup"]
        delay = rl["backoff_initial_s"]
        attempt = 0
        while True:
            try:
                self.n_calls += 1
                return await self._generate(role, model, prompt, schema, key_bump=attempt), model
            except asyncio.TimeoutError:
                if model == backup:
                    raise
                model = backup
            except Exception as e:  # noqa: BLE001
                if not _is_transient(e) or (model == backup and attempt > rl["max_429_retries"]):
                    raise
                attempt += 1
                if attempt > rl["max_429_retries"] and model != backup:
                    model = backup
                    continue
                await asyncio.sleep(min(delay, rl["backoff_max_s"]) * (0.8 + 0.4 * random.random()))
                delay *= 2

    async def position(self, role: str, prompt: str, response_model: type, round: int,
                       call: AgentCall | None = None) -> AgentMessage:
        model = self.model_for(role)
        t0 = time.monotonic()
        ms = lambda: int((time.monotonic() - t0) * 1000)  # noqa: E731
        if not killswitch.llm_enabled():
            return AgentMessage(agent=role, round=round, status="killed", position=None, model=model,
                                latency_ms=0, errors=["LLM disabled by kill switch"])
        schema = response_model.model_json_schema()
        tin = tout = 0
        errors: list[str] = []
        cur_prompt = prompt
        retries_allowed = self.cfg["negotiation"]["schema_retries"]
        for attempt in range(retries_allowed + 1):
            if not killswitch.llm_enabled():
                return AgentMessage(agent=role, round=round, status="killed", position=None, model=model,
                                    latency_ms=ms(), errors=["LLM disabled by kill switch"], retries=attempt)
            try:
                resp, model = await self._generate_with_backoff(role, cur_prompt, schema)
            except asyncio.TimeoutError:
                return AgentMessage(agent=role, round=round, status="timeout", position=None, model=model,
                                    latency_ms=ms(), errors=["call timed out"], retries=attempt,
                                    tokens_in=tin or None, tokens_out=tout or None)
            except Exception as e:  # noqa: BLE001
                status = "rate_limited" if _is_429(e) else "error"
                return AgentMessage(agent=role, round=round, status=status, position=None, model=model,
                                    latency_ms=ms(), errors=[f"{type(e).__name__}: {str(e)[:200]}"],
                                    retries=attempt, tokens_in=tin or None, tokens_out=tout or None)
            um = getattr(resp, "usage_metadata", None)
            if um:
                tin += um.prompt_token_count or 0
                tout += (um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
            try:
                raw = json.loads(resp.text or "")
                pos, errors = validate_position(raw, call.ctx) if call else _plain_validate(raw)
            except (ValueError, TypeError) as e:
                pos, errors = None, [f"invalid JSON: {str(e)[:120]}"]
            if pos is not None:
                return AgentMessage(agent=role, round=round, status="ok", position=pos, model=model,
                                    latency_ms=ms(), tokens_in=tin or None, tokens_out=tout or None,
                                    retries=attempt)
            cur_prompt = (prompt + "\n\nYour previous answer was rejected by the validator:\n- "
                          + "\n- ".join(errors[:8]) + "\nAnswer again with valid JSON only.")
        return AgentMessage(agent=role, round=round, status="schema_fail", position=None, model=model,
                            latency_ms=ms(), errors=errors, tokens_in=tin or None, tokens_out=tout or None,
                            retries=retries_allowed)

    async def text(self, role: str, prompt: str) -> tuple[str, str]:
        """Plain-text call (narrator). Returns (text, model)."""
        if not killswitch.llm_enabled():
            raise RuntimeError("LLM disabled by kill switch")
        resp, model = await self._generate_with_backoff(role, prompt, None)
        return (resp.text or "").strip(), model


def _plain_validate(raw: dict):
    from pydantic import ValidationError
    try:
        return AgentPosition.model_validate(raw), []
    except ValidationError as e:
        return None, [str(e)[:200]]


# ----------------------------------------------------------------------------------------------
# MockLLMClient: deterministic, no network. Ranks by sorting the existing metrics per role goals.

def _role_key(role: str) -> Callable:
    if role == "ATC":
        return lambda o: (o.metrics.bank_delay_added_min, -o.metrics.separation_margin_s, o.option_id)
    if role == "PILOT":
        return lambda o: (o.metrics.misconnected_pax, o.metrics.extra_fuel_min, o.option_id)
    return lambda o: (o.metrics.ramp_overtime_min, -o.metrics.turnaround_buffer_min, o.option_id)


ROLE_CITES = {"ATC": "bank_delay_added_min", "PILOT": "misconnected_pax", "GROUND": "turnaround_buffer_min"}


class MockLLMClient:
    """mode: "normal" (consensus by R2), "deadlock" (PILOT and GROUND reject everything after R1),
    "unsafe" (all agents push an infeasible option first; the checker must veto it)."""

    def __init__(self, mode: str = "normal", config: dict | None = None, top_k: int = 3):
        self.mode = mode
        self.cfg = config or load_config()
        self.top_k = top_k
        self.n_calls = 0
        self._countered: set[str] = set()

    def model_for(self, role: str) -> str:
        return "mock"

    async def position(self, role: str, prompt: str, response_model: type, round: int,
                       call: AgentCall | None = None) -> AgentMessage:
        if not killswitch.llm_enabled():
            return AgentMessage(agent=role, round=round, status="killed", position=None, model="mock",
                                latency_ms=0, errors=["LLM disabled by kill switch"])
        self.n_calls += 1
        await asyncio.sleep(0)
        v = call.view
        opts = [v["options"][i] for i in v["candidates"]]
        checks = v["checks"]
        feasible = [o for o in opts if checks[o.option_id].feasible]
        ranked = sorted(opts, key=_role_key(role))
        acceptable = [o.option_id for o in sorted(feasible, key=_role_key(role))[: self.top_k]]
        ranking = [o.option_id for o in ranked]
        tentative = v["tentative"]
        counter = None
        red = {"ATC": ["H1_wake_separation", "H2_runway_capacity"], "PILOT": ["H3_fuel_reserve"],
               "GROUND": ["H4_gate_validity"]}[role]

        if self.mode == "unsafe":
            bad = [o.option_id for o in opts if not checks[o.option_id].feasible]
            if bad:
                ranking = [bad[0]] + [i for i in ranking if i != bad[0]]
                acceptable = [bad[0]]

        if v["ballot"] or round >= 2:
            ok = tentative is not None and tentative in acceptable
            if self.mode == "deadlock" and role in ("PILOT", "GROUND"):
                ok, acceptable = False, []
            if self.mode == "unsafe" and v["ballot"]:
                ok = tentative is not None   # rubber-stamps whatever is on the ballot
            action = "ACCEPT" if ok else "REJECT"
            if ok and tentative not in acceptable:
                acceptable = [tentative] + acceptable
        else:
            action = "PROPOSE"
            if role == "GROUND" and self.mode == "normal" and "GROUND" not in self._countered:
                counter = self._gate_counter(v, feasible, role)
                if counter:
                    action = "COUNTER"
                    self._countered.add("GROUND")
        top = ranking[0] if ranking else None
        cites = [f"{top}.{ROLE_CITES[role]}"] if top else []
        rationale = (f"{role} prefers {top} on {ROLE_CITES[role]} (see {cites[0]})." if top
                     else f"{role} has no candidate.")
        if action == "REJECT":
            rationale = f"{role} rejects {tentative}: outside its acceptable set."
        if action == "ACCEPT":
            rationale = f"{role} accepts {tentative}; it is within its acceptable set."
        if counter:
            rationale = (f"{role} counters {counter.base_option} with gate {counter.value} "
                         f"to protect turnaround (see {cites[0]}).")
        pos = AgentPosition(agent=role, round=round, action=action, ranking=ranking,
                            acceptable=acceptable, counter=counter, red_lines=red, cites=cites,
                            rationale=rationale[:300])
        vpos, errors = validate_position(pos.model_dump(mode="json"), call.ctx)
        if vpos is None:
            return AgentMessage(agent=role, round=round, status="schema_fail", position=None, model="mock",
                                latency_ms=1, errors=errors)
        return AgentMessage(agent=role, round=round, status="ok", position=vpos, model="mock", latency_ms=1,
                            tokens_in=0, tokens_out=0)

    @staticmethod
    def _gate_counter(v: dict, feasible: list, role: str) -> Counter | None:
        """GROUND's one counter: move its best feasible option to another gate that is free (by the
        scenario's occupancy intervals) and size-compatible. The checker still validates it."""
        if not feasible:
            return None
        s = v["scenario"]
        base = sorted(feasible, key=_role_key(role))[0]
        eta = base.metrics.eta_new_min
        end = s.next_departure_min or eta + 60
        size_rank = {"S": 0, "M": 1, "L": 2}
        used = {(o.eta_shift_min, o.gate, o.fp_adjustment) for o in v["options"].values()}
        for g in s.gates:
            if g.gate_id == base.gate or g.gate_id not in v["allowed"]["gate"] or g.out_of_service:
                continue
            if size_rank[g.size] < size_rank[s.aircraft_size]:
                continue
            if set(g.taxi_path) & set(s.blocked_taxiways):
                continue
            if any(a < end and eta < b for a, b in g.occupied):
                continue
            if (base.eta_shift_min, g.gate_id, base.fp_adjustment) in used:
                continue
            return Counter(base_option=base.option_id, param="gate", value=g.gate_id)
        return None
