"""LLM clients. One call = one agent. GeminiClient (live) and MockLLMClient (offline, deterministic).

Neither client computes numbers or checks legality: Gemini ranks the pre-computed table; the mock
ranks by sorting existing metrics. All validation happens in agents.schema.validate_position.
"""
import asyncio
import json
import os
import random
import sys
import time
from typing import Callable, Protocol

from dotenv import dotenv_values

from core.config import load_config, repo_path
from agents import budget, callcount, killswitch
from agents.prompting import AgentCall
from agents.schema import AgentMessage, AgentPosition, Counter, validate_position


class LLMClient(Protocol):
    async def position(self, role: str, prompt: str, response_model: type, round: int,
                       call: AgentCall | None = None) -> AgentMessage: ...


KEY_NAMES = ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3")
CALLS_TODAY = 0   # real API requests made by THIS process (incl. retries); the budget ledger has the cross-process count


def _api_keys() -> list[tuple[str, str]]:
    """[(env name, key)] for GEMINI_API_KEY, _2, _3 from .env (process env overrides). Keys are never logged."""
    file_vals = dotenv_values(repo_path(".env")) if os.path.exists(repo_path(".env")) else {}
    keys = []
    for name in KEY_NAMES:
        v = os.environ[name] if name in os.environ else file_vals.get(name)   # env (even empty) wins
        if v and v.strip() and "your" not in v.lower():
            keys.append((name, v.strip()))
    return keys


def _is_429(e: Exception) -> bool:
    return getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e)[:300]


def _is_transient(e: Exception) -> bool:
    """429 rate limit or 503 overload: back off (max_429_retries times), then fail as rate_limited."""
    return _is_429(e) or getattr(e, "code", None) in (500, 503) or "UNAVAILABLE" in str(e)[:300]


def parse_json_text(text: str):
    """Parse a JSON object from model text (prompt-only mode may wrap it in ``` fences or prose)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except ValueError:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise


def make_llm(mode: str | None = None, config: dict | None = None):
    """For the API/UI: mode None or "live" -> GeminiClient; "mock"/"normal"/"deadlock"/"unsafe"/
    "hallucinate" -> scripted MockLLMClient."""
    if mode in (None, "live"):
        return GeminiClient(config)
    return MockLLMClient("normal" if mode == "mock" else mode, config=config)


class GeminiClient:
    """google-genai async client, one request per agent call (+ at most 1 schema retry and
    max_429_retries back-offs). No model cascade. JSON-schema output when the model supports it
    (config `structured_output: {model: bool}`, default true), else prompt-only JSON + code validation."""

    ROLE_KEY_INDEX = {"ATC": 0, "PILOT": 1, "GROUND": 2, "NARRATOR": 0}
    scripted = False
    THINKING_LEVEL = "low"   # ranking a precomputed table needs little reasoning; keeps latency < timeout

    def __init__(self, config: dict | None = None):
        from google import genai
        self.cfg = config or load_config()
        keys = _api_keys()
        if not keys:
            raise RuntimeError("GEMINI_API_KEY missing in .env")
        self.key_names = [n for n, _ in keys]
        self._clients = {n: genai.Client(api_key=k) for n, k in keys}
        self.n_calls = 0
        self._no_thinking: set[str] = set()   # models that reject thinking_config
        print(f"LLM_CLIENT keys={self.key_names} calls_this_process={CALLS_TODAY}", file=sys.stderr)

    def model_for(self, role: str) -> str:
        return self.cfg["models"][role]

    def structured(self, model: str) -> bool:
        return bool((self.cfg.get("structured_output") or {}).get(model, True))

    def _keys_for(self, role: str) -> list[str]:
        i = self.ROLE_KEY_INDEX.get(role, 0) % len(self.key_names)
        return self.key_names[i:] + self.key_names[:i]

    async def _raw_request(self, key_name: str, model: str, prompt: str, schema: dict | None):
        """Exactly one real API request."""
        from google.genai import types
        global CALLS_TODAY
        neg = self.cfg["negotiation"]
        kw = dict(temperature=neg["temperature"])
        if schema is not None:
            kw.update(response_mime_type="application/json", response_json_schema=schema)
        if model not in self._no_thinking:
            kw["thinking_config"] = types.ThinkingConfig(thinking_level=self.THINKING_LEVEL)
        self.n_calls += 1
        CALLS_TODAY += 1
        callcount.bump()
        try:
            return await asyncio.wait_for(
                self._clients[key_name].aio.models.generate_content(
                    model=model, contents=prompt, config=types.GenerateContentConfig(**kw)),
                timeout=neg["call_timeout_s"])
        except Exception as e:  # noqa: BLE001
            if getattr(e, "code", None) == 400 and "hinking" in str(e) and model not in self._no_thinking:
                self._no_thinking.add(model)
                raise _RetryWithoutThinking() from e
            raise

    async def _budgeted_key(self, role: str, model: str) -> str:
        """Reserve one request in the shared ledger (waits on the RPM limiter). Role's own key first,
        then the others. Raises BudgetExhausted when every key is at its daily cap."""
        for key in self._keys_for(role):
            ok, used, cap = await budget.acquire(key, self.cfg)
            if ok:
                print(f"LLM_CALL key={key} model={model} used={used}/{cap}", file=sys.stderr)
                return key
        raise BudgetExhausted("daily LLM budget exhausted")

    async def _request(self, role: str, model: str, prompt: str, schema: dict | None):
        key = await self._budgeted_key(role, model)
        try:
            return await self._raw_request(key, model, prompt, schema)
        except _RetryWithoutThinking:
            key = await self._budgeted_key(role, model)
            return await self._raw_request(key, model, prompt, schema)

    def budget_remaining(self) -> int:
        """Calls left today across this client's keys (the coordinator refuses to start below one run)."""
        return budget.remaining(self.key_names, self.cfg)

    async def _generate_with_backoff(self, role: str, prompt: str, schema: dict | None):
        """429/503: back off max_429_retries times, then raise (-> rate_limited). Timeouts raise."""
        rl = self.cfg["rate_limit"]
        model = self.model_for(role)
        delay = rl["backoff_initial_s"]
        for attempt in range(rl["max_429_retries"] + 1):
            try:
                return await self._request(role, model, prompt, schema)
            except BudgetExhausted:
                raise
            except Exception as e:  # noqa: BLE001
                if not _is_transient(e) or attempt >= rl["max_429_retries"]:
                    raise
                await asyncio.sleep(min(delay, rl["backoff_max_s"]) * (0.8 + 0.4 * random.random()))
                delay *= 2
        raise RuntimeError("unreachable")

    async def position(self, role: str, prompt: str, response_model: type, round: int,
                       call: AgentCall | None = None) -> AgentMessage:
        model = self.model_for(role)
        t0 = time.monotonic()
        ms = lambda: int((time.monotonic() - t0) * 1000)  # noqa: E731
        if not killswitch.llm_enabled():
            return AgentMessage(agent=role, round=round, status="killed", position=None, model=model,
                                latency_ms=0, errors=["LLM disabled by kill switch"])
        json_schema = response_model.model_json_schema()
        if self.structured(model):
            schema, base_prompt = json_schema, prompt
        else:   # prompt-only JSON: the schema goes into the prompt, code validates
            schema = None
            base_prompt = (prompt + "\n\nReturn ONLY a JSON object (no prose, no code fences) matching this "
                           "JSON schema:\n" + json.dumps(json_schema, separators=(",", ":")))
        tin = tout = 0
        errors: list[str] = []
        cur_prompt = base_prompt
        retries_allowed = self.cfg["negotiation"]["schema_retries"]
        for attempt in range(retries_allowed + 1):
            if not killswitch.llm_enabled():
                return AgentMessage(agent=role, round=round, status="killed", position=None, model=model,
                                    latency_ms=ms(), errors=["LLM disabled by kill switch"], retries=attempt)
            try:
                resp = await self._generate_with_backoff(role, cur_prompt, schema)
            except asyncio.TimeoutError:
                return AgentMessage(agent=role, round=round, status="timeout", position=None, model=model,
                                    latency_ms=ms(), errors=["call timed out"], retries=attempt,
                                    tokens_in=tin or None, tokens_out=tout or None)
            except BudgetExhausted as e:
                return AgentMessage(agent=role, round=round, status="rate_limited", position=None, model=model,
                                    latency_ms=ms(), errors=[str(e)], retries=attempt,
                                    tokens_in=tin or None, tokens_out=tout or None)
            except Exception as e:  # noqa: BLE001
                status = "rate_limited" if _is_transient(e) else "error"
                return AgentMessage(agent=role, round=round, status=status, position=None, model=model,
                                    latency_ms=ms(), errors=[f"{type(e).__name__}: {str(e)[:200]}"],
                                    retries=attempt, tokens_in=tin or None, tokens_out=tout or None)
            um = getattr(resp, "usage_metadata", None)
            if um:
                tin += um.prompt_token_count or 0
                tout += (um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
            try:
                raw = parse_json_text(resp.text or "")
                pos, errors = validate_position(raw, call.ctx) if call else _plain_validate(raw)
            except (ValueError, TypeError) as e:
                pos, errors = None, [f"invalid JSON: {str(e)[:120]}"]
            if pos is not None:
                return AgentMessage(agent=role, round=round, status="ok", position=pos, model=model,
                                    latency_ms=ms(), tokens_in=tin or None, tokens_out=tout or None,
                                    retries=attempt)
            cur_prompt = (base_prompt + "\n\nYour previous answer was rejected by the validator:\n- "
                          + "\n- ".join(errors[:8]) + "\nAnswer again with valid JSON only.")
        return AgentMessage(agent=role, round=round, status="schema_fail", position=None, model=model,
                            latency_ms=ms(), errors=errors, tokens_in=tin or None, tokens_out=tout or None,
                            retries=retries_allowed)

    async def text(self, role: str, prompt: str) -> tuple[str, str]:
        """Plain-text call (narrator). Returns (text, model)."""
        if not killswitch.llm_enabled():
            raise RuntimeError("LLM disabled by kill switch")
        resp = await self._generate_with_backoff(role, prompt, None)
        return (resp.text or "").strip(), self.model_for(role)


class _RetryWithoutThinking(Exception):
    pass


class BudgetExhausted(Exception):
    pass


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
    """Scripted agents (labelled `scripted: true` in run_started). mode:
    "normal" (consensus by R2), "deadlock" (PILOT and GROUND reject everything after R1 -> fallback),
    "unsafe" (all agents push an H3-failing option -> veto -> fallback),
    "hallucinate" (PILOT cites a non-existent option/gate in R1 -> validation rejects it -> REJECT;
    ATC's R1 rationale states a number its cited metric doesn't have -> ungrounded: true)."""

    MODES = ("normal", "deadlock", "unsafe", "hallucinate")
    scripted = True

    def __init__(self, mode: str = "normal", config: dict | None = None, top_k: int = 3):
        if mode not in self.MODES:
            raise ValueError(f"unknown mock mode {mode!r}; one of {self.MODES}")
        self.mode = mode
        self.cfg = config or load_config()
        self.top_k = top_k
        self.n_calls = 0
        self._countered: set[str] = set()
        self._acceptable: dict[str, list[str]] = {}   # per role, fixed in R1 (stable preferences)

    def model_for(self, role: str) -> str:
        return "mock"

    async def position(self, role: str, prompt: str, response_model: type, round: int,
                       call: AgentCall | None = None) -> AgentMessage:
        if not killswitch.llm_enabled():
            return AgentMessage(agent=role, round=round, status="killed", position=None, model="mock",
                                latency_ms=0, errors=["LLM disabled by kill switch"])
        self.n_calls += 1
        callcount.bump()
        await asyncio.sleep(0)
        v = call.view
        opts = [v["options"][i] for i in v["candidates"]]
        checks = v["checks"]
        feasible = [o for o in opts if checks[o.option_id].feasible]
        ranked = sorted(opts, key=_role_key(role))
        acceptable = [o.option_id for o in sorted(feasible, key=_role_key(role))[: self.top_k]]
        if round == 1 or role not in self._acceptable:
            self._acceptable[role] = acceptable
        else:
            acceptable = [i for i in self._acceptable[role] if i in v["candidates"]]
        ranking = [o.option_id for o in ranked]
        if round >= 2:   # after R1 the mock only ranks options the checker passed
            ranking = [i for i in ranking if checks[i].feasible]
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
        if self.mode == "hallucinate" and role == "ATC" and round == 1 and top:
            # scripted failure case: a number the cited metric doesn't support (coordinator flags it)
            wrong = v["options"][top].metrics.bank_delay_added_min + 7
            rationale = f"{role} prefers {top}: it adds only {wrong} min of bank delay (see {cites[0]})."
        pos = AgentPosition(agent=role, round=round, action=action, ranking=ranking,
                            acceptable=acceptable, counter=counter, red_lines=red, cites=cites,
                            rationale=rationale[:300])
        raw = pos.model_dump(mode="json")
        retries = 0
        if self.mode == "hallucinate" and role == "PILOT" and round == 1:
            # scripted failure case §8.4 #3: a non-existent option and gate. Gemini's enum schema makes
            # this unlikely live, so it is shown scripted. The mock "retries" once, as the real client would.
            raw["ranking"] = ["opt_9"] + raw["ranking"]
            raw["cites"] = raw["cites"] + ["opt_4.gate_Z9"]
            raw["rationale"] = "PILOT prefers opt_9 at gate Z9 (see opt_4.gate_Z9)."
            self.n_calls += 1
            callcount.bump()
            retries = 1
        vpos, errors = validate_position(raw, call.ctx)
        if vpos is None:
            return AgentMessage(agent=role, round=round, status="schema_fail", position=None, model="mock",
                                latency_ms=1, errors=errors, retries=retries)
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
