"""Agent message types (CONTRACTS.md §2) + per-scenario response models and code-side validation.

The LLM only ranks pre-computed options and cites metrics. Everything it returns is validated here
by code: option ids, metric refs, counter grid, round rules. Any error -> the message counts as REJECT.
"""
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, create_model

from core.types import AgentRole, ConstraintId, Metrics

MAX_ROUNDS_HARD = 3   # the protocol never allows more; config MAX_ROUNDS is asserted <= this

ACTIONS_BY_ROUND: dict[int, tuple[str, ...]] = {
    1: ("PROPOSE", "COUNTER"),
    2: ("ACCEPT", "REJECT", "COUNTER"),
    3: ("ACCEPT", "REJECT"),
}
PHASE_BY_ROUND = {1: "PROPOSE", 2: "RESPOND", 3: "BALLOT"}
COUNTER_PARAMS = ("eta_shift_min", "gate", "fp_adjustment")
METRIC_NAMES = tuple(Metrics.model_fields)   # every metric an agent may cite as opt_id.metric
RATIONALE_MAX = 300


class Counter(BaseModel):
    base_option: str                 # must be an existing option_id (enum per scenario)
    param: Literal["eta_shift_min", "gate", "fp_adjustment"]
    value: str | int                 # must be in counter_allowed_values(s)[param]


class AgentPosition(BaseModel):
    agent: AgentRole
    round: Literal[1, 2, 3]
    action: Literal["PROPOSE", "COUNTER", "ACCEPT", "REJECT"]
    ranking: list[str]               # option_ids, best first, subset of candidates
    acceptable: list[str]            # option_ids this agent can live with
    counter: Counter | None = None   # rounds 1–2 only
    red_lines: list[ConstraintId] = []
    cites: list[str] = []            # MetricRef "opt_3.fuel_at_landing_min"
    rationale: str = Field(max_length=RATIONALE_MAX)


class AgentMessage(BaseModel):       # what the coordinator records/streams for each agent call
    agent: AgentRole
    round: int
    status: Literal["ok", "schema_fail", "timeout", "rate_limited", "error", "killed"]
    position: AgentPosition | None   # None unless status == "ok"; non-ok counts as REJECT
    errors: list[str] = []           # validation errors (e.g. "unknown option opt_9")
    model: str
    latency_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    retries: int = 0
    ungrounded: bool = False         # stretch: rationale numbers don't match cited metrics


def metric_refs_for(option_ids: list[str]) -> list[str]:
    return [f"{o}.{m}" for o in option_ids for m in METRIC_NAMES]


def build_position_model(option_ids: list[str], metric_refs: list[str], round: int,
                         agent: str | None = None, max_rounds: int = MAX_ROUNDS_HARD,
                         ballot: bool = False) -> type[BaseModel]:
    """Response schema for one agent call. OptionId / MetricRef are Literal enums of THIS scenario's
    ids, so Gemini's constrained decoding cannot produce an unknown option. The counter field does
    not exist in the ballot round (round == max_rounds)."""
    OptionId = Literal[tuple(option_ids)]  # type: ignore[valid-type]
    MetricRef = Literal[tuple(metric_refs)] if metric_refs else str  # type: ignore[valid-type]
    ballot = ballot or round >= max_rounds
    actions = ACTIONS_BY_ROUND[3] if ballot else ACTIONS_BY_ROUND[min(round, 2)]
    fields: dict = {
        "agent": (Literal[agent] if agent else AgentRole, ...),  # type: ignore[valid-type]
        "round": (Literal[round], ...),  # type: ignore[valid-type]
        "action": (Literal[actions], ...),  # type: ignore[valid-type]
        "ranking": (list[OptionId], Field(..., description="option ids, best first")),
        "acceptable": (list[OptionId], Field(..., description="option ids you can live with")),
        "red_lines": (list[ConstraintId], Field(default_factory=list)),
        "cites": (list[MetricRef], Field(default_factory=list, description="opt_id.metric refs")),
        "rationale": (str, Field(..., max_length=RATIONALE_MAX)),
    }
    if not ballot:
        CounterModel = create_model(
            f"CounterR{round}",
            base_option=(OptionId, ...),
            param=(Literal[COUNTER_PARAMS], ...),  # type: ignore[valid-type]
            value=(str, Field(..., description="allowed value as text, e.g. '15', 'B2', 'speed_reduction'")),
        )
        fields["counter"] = (Optional[CounterModel], None)
    return create_model(f"Position_{agent or 'ANY'}_R{round}", **fields)


@dataclass
class ValidationCtx:
    agent: str
    round: int
    candidates: list[str]                    # option ids the agent may rank/accept this round
    option_ids: list[str]                    # every known option id (counter base must be one)
    metric_refs: list[str]
    allowed_values: dict[str, list]          # counter_allowed_values(s)
    tentative: str | None = None
    max_rounds: int = MAX_ROUNDS_HARD
    ballot: bool = False                     # early ballot (empty agreement set) before max_rounds
    extra: dict = field(default_factory=dict)


def _coerce_counter_value(param: str, value, allowed: list):
    if param == "eta_shift_min":
        try:
            return int(str(value).strip().lstrip("+"))
        except ValueError:
            return value
    return str(value).strip()


def validate_position(raw: dict, ctx: ValidationCtx) -> tuple[AgentPosition | None, list[str]]:
    """Code-side checks on a raw JSON position. Returns (position, []) or (None, errors)."""
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, ["response is not a JSON object"]
    raw = dict(raw)
    if isinstance(raw.get("rationale"), str) and len(raw["rationale"]) > RATIONALE_MAX:
        raw["rationale"] = raw["rationale"][:RATIONALE_MAX]
    if raw.get("counter") and isinstance(raw["counter"], dict):
        c = dict(raw["counter"])
        if c.get("param") in COUNTER_PARAMS:
            c["value"] = _coerce_counter_value(c["param"], c.get("value"),
                                               ctx.allowed_values.get(c["param"], []))
        raw["counter"] = c
    elif raw.get("counter") is not None and not isinstance(raw.get("counter"), dict):
        errors.append("counter must be an object or null")
        raw["counter"] = None
    try:
        pos = AgentPosition.model_validate(raw)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            errors.append(f"schema: {loc}: {err['msg']}")
        return None, errors

    if pos.agent != ctx.agent:
        errors.append(f"agent is {pos.agent}, expected {ctx.agent}")
    if pos.round != ctx.round:
        errors.append(f"round is {pos.round}, expected {ctx.round}")
    ballot = ctx.ballot or ctx.round >= ctx.max_rounds
    allowed_actions = ACTIONS_BY_ROUND[3] if ballot else ACTIONS_BY_ROUND[min(ctx.round, 2)]
    # R1: a PROPOSE that carries a counter is a COUNTER
    if ctx.round == 1 and pos.action == "PROPOSE" and pos.counter is not None:
        pos.action = "COUNTER"
    if pos.action not in allowed_actions:
        errors.append(f"action {pos.action} not allowed in round {ctx.round} (allowed: {', '.join(allowed_actions)})")

    known = set(ctx.option_ids)
    cand = set(ctx.candidates)
    for name, ids in (("ranking", pos.ranking), ("acceptable", pos.acceptable)):
        for oid in ids:
            if oid not in known:
                errors.append(f"unknown option {oid}")
            elif oid not in cand:
                errors.append(f"{name}: {oid} is not a candidate this round")
        if len(set(ids)) != len(ids):
            errors.append(f"{name} has duplicates")
    refs = set(ctx.metric_refs)
    for ref in pos.cites:
        if ref not in refs:
            errors.append(f"unknown metric ref {ref}")

    if pos.counter is not None:
        c = pos.counter
        if ballot:
            errors.append(f"counter not allowed in round {ctx.round} (ballot only)")
        if c.base_option not in known:
            errors.append(f"unknown option {c.base_option}")
        allowed = ctx.allowed_values.get(c.param, [])
        if c.value not in allowed:
            errors.append(f"counter value {c.value!r} for {c.param} is off-grid (allowed: {allowed})")
    elif pos.action == "COUNTER":
        errors.append("action COUNTER requires a counter")
    if pos.counter is not None and pos.action != "COUNTER" and not ballot:
        errors.append(f"counter given with action {pos.action}; use action COUNTER")

    if errors:
        return None, list(dict.fromkeys(errors))
    return pos, []


# ---- grounding check (proposal §4.2): a flag, never a rejection --------------------------------
_ROUND_REF = re.compile(r"\bround\s+[1-3]\b", re.IGNORECASE)
# a number not glued to a preceding identifier (opt_3, opt_c1, H3, R2, gate B2, Z9 are skipped);
# HH:MM is read as minutes after midnight, like the *_min metrics
_NUMBER = re.compile(r"(?<![\w.])(?:(\d{1,2}):(\d{2})\b|(\d+(?:,\d{3})*(?:\.\d+)?))")


def rationale_numbers(text: str) -> list[tuple[str, float, int]]:
    """[(token, value, decimals)] for every number in a rationale (sign dropped)."""
    out = []
    for m in _NUMBER.finditer(_ROUND_REF.sub(" ", text or "")):
        if m.group(1) is not None:
            out.append((m.group(0), int(m.group(1)) * 60 + int(m.group(2)), 0))
        else:
            tok = m.group(3)
            dec = len(tok.split(".", 1)[1]) if "." in tok else 0
            out.append((tok, float(tok.replace(",", "")), dec))
    return out


def _rounds_to(v: float, x: float, dec: int) -> bool:
    """v rounded half-up to `dec` decimals equals x."""
    h = 0.5 * 10 ** -dec
    return -h - 1e-9 <= v - x < h - 1e-9


def ungrounded_numbers(rationale: str, cites: list[str], options: dict) -> list[str]:
    """Numbers in the rationale that match no CITED metric (equal after rounding to the precision the
    agent wrote). A cited option's eta_shift_min (its table column) also counts. Uncited metrics don't."""
    values: list[float] = []
    for ref in cites:
        oid, _, name = ref.partition(".")
        o = options.get(oid)
        if o is None:
            continue
        for v in (getattr(o.metrics, name, None), o.eta_shift_min):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                values.append(abs(float(v)))
    return [tok for tok, x, dec in rationale_numbers(rationale)
            if not any(_rounds_to(v, x, dec) for v in values)]
