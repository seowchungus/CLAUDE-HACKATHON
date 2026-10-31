# ACCORD Contracts (FROZEN v1.2, 2026-10-31 12:55 +08; v1.1 12:25; v1.0 11:20)

Owner: MANAGER. Every worker builds against this file exactly.
Changes after the freeze go through MANAGER only and are recorded in the "Changelog" at the bottom and in `.team/BOARD.md`.
Where this file is silent, `ACCORD_proposal.md` decides.

Fixtures that conform to this file (use them for mocks until integration):
- `docs/fixtures/scenario_bundle.json`: one `ScenarioBundle` plus `map` (the `GET /api/scenarios/{id}` response)
- `docs/fixtures/run_events.jsonl`: one full run as SSE envelopes, one per line (R1 counter vetoed, consensus in R2)
- `docs/fixtures/scenarios_list.json`: the `GET /api/scenarios` response
- `docs/fixtures/run_log.jsonl`: the hash-chained log matching `run_events.jsonl` (verifies with §5)

The fixtures are hand-made and labelled `"fixture": true`. They are not real DOT rows.

---

## 0. Conventions

- Python 3.11+, Pydantic v2 `BaseModel` for every type below. Serialise with `model_dump(mode="json")`.
- **Times:** `int` minutes after local midnight of the flight date at the airport concerned (may exceed 1440 for after-midnight). Field names end in `_min`. Display as `HH:MM` in the UI only.
- **Durations:** `int` or `float` minutes, field names end in `_min`; seconds end in `_s`.
- **IDs:**
  - `scenario_id = f"{YYYY}-{MM:02}-{DD:02}_{AIRLINE}{FLIGHT_NUMBER}_{ORIGIN}-{DEST}"`, e.g. `2015-01-02_AA1234_DFW-ORD`
  - `option_id`: generated `opt_1..opt_8`; counters `opt_c1, opt_c2…` (in order of acceptance); FCFS baseline `opt_fcfs` (never a negotiation candidate)
  - `run_id`: `run_<YYYYMMDDTHHMMSS>_<6 hex>`
  - `flight_id = f"{AIRLINE}{FLIGHT_NUMBER}"`, **unpadded** (`UA918`, never `UA0918`); same in `scenario_id`. Parsers may accept padded input. If two rows share a scenario_id, take the first.
- **Roles:** `AgentRole = Literal["ATC", "PILOT", "GROUND"]`
- **Constraint IDs** (exact strings):
  `ConstraintId = Literal["H1_wake_separation", "H2_runway_capacity", "H3_fuel_reserve", "H4_gate_validity", "H5_crew_duty", "H6_taxiway_reachability", "H7_severe_turbulence"]`
- **Flight plan adjustments:** `FPAdj = Literal["as_filed", "speed_reduction", "hold_10", "hold_20", "reroute_weather"]`
- **Counter grid:** `eta_shift_min ∈ config.options.eta_shifts_min` (0..60 step 5), `gate ∈ scenario gate_ids`, `fp_adjustment ∈ FPAdj`.
- **Provenance:** `Provenance = Literal["real", "real_derived", "estimated", "synthetic"]`. Every non-real field is listed in `Scenario.provenance` and the UI shows a `SYNTHETIC` tag next to it. *(v1.1)* Keys are top-level field names, plus dotted `<field>.<subfield>` keys for sub-fields of nested/list items. **Required keys:** `row, disruption_type, disruption_min, origin, destination, disrupted, bank, connections, base_eta_min, aar_nominal, aar_reduced, aircraft_size, fuel_at_fix_min, flight_crew_duty_remaining_min, ramp_shift_end_min, next_departure_min, gates, taxiways, blocked_taxiways, turbulence_by_fp, chaos_applied, disrupted.wake, bank.wake, connections.wake, connections.pax_connecting`, and from v1.2 `airport_limits, planned_gate, decision_time_min`. `apply_chaos` sets every field it touches to `synthetic`.
- Thresholds, weights and model names come from `config.yaml`, loaded with `core.config.load_config() -> dict` (W1 provides it).

---

## 1. Core types: `core/types.py` (W1 owns; W2/W3 import, never redefine)

```python
from typing import Literal
from pydantic import BaseModel, Field

AgentRole = Literal["ATC", "PILOT", "GROUND"]
ConstraintId = Literal["H1_wake_separation", "H2_runway_capacity", "H3_fuel_reserve",
                       "H4_gate_validity", "H5_crew_duty", "H6_taxiway_reachability",
                       "H7_severe_turbulence"]
FPAdj = Literal["as_filed", "speed_reduction", "hold_10", "hold_20", "reroute_weather"]
WakeCat = Literal["H", "M", "L"]
SizeClass = Literal["S", "M", "L"]
Provenance = Literal["real", "real_derived", "estimated", "synthetic"]
FlightRole = Literal["disrupted", "bank", "connection"]
ChaosKind = Literal["RUNWAY_CLOSURE", "TAXIWAY_BLOCK", "GATE_FAILURE", "WEATHER_CELL"]

class DotRow(BaseModel):            # verbatim from flights.csv (REAL). Times are raw HHMM ints as in the CSV.
    year: int; month: int; day: int
    airline: str
    flight_number: int
    tail_number: str | None
    origin: str
    destination: str
    scheduled_departure: int        # HHMM
    departure_delay: float | None
    scheduled_arrival: int          # HHMM
    arrival_delay: float | None
    distance: int
    scheduled_time: float | None
    air_time: float | None
    taxi_in: float | None
    taxi_out: float | None
    weather_delay: float | None
    late_aircraft_delay: float | None
    air_system_delay: float | None

class Airport(BaseModel):            # REAL, from airports.csv
    iata: str; name: str; city: str; state: str
    lat: float; lon: float

class FlightRef(BaseModel):          # disrupted flight, arrival-bank flight, or at-risk connection
    flight_id: str                   # "AA1234"
    airline: str
    flight_number: int
    tail_number: str | None
    origin: str
    destination: str
    sched_dep_min: int               # REAL
    sched_arr_min: int               # REAL
    est_arr_min: int | None          # REAL for bank (sched_arr + ARRIVAL_DELAY); None for connections
    role: FlightRole
    wake: WakeCat                    # SYNTHETIC
    pax_connecting: int | None = None  # SYNTHETIC, connections only (pax from the disrupted flight)

class Gate(BaseModel):               # SYNTHETIC template per airport
    gate_id: str                     # "A1".."C4"
    concourse: str
    size: SizeClass
    taxi_path: list[str]             # taxiway IDs used to reach it, e.g. ["A", "C"]
    occupied: list[tuple[int, int]]  # [start_min, end_min) busy intervals
    out_of_service: bool = False

class ChaosEvent(BaseModel):
    kind: ChaosKind
    params: dict = {}                # RUNWAY_CLOSURE {"aar_factor":0.5}; TAXIWAY_BLOCK {"taxiway":"B"};
                                     # GATE_FAILURE {"gate_id":"B2","duration_min":90}; WEATHER_CELL {"turbulence_add":0.3,"extra_delay_min":15}
    note: str = ""

class Scenario(BaseModel):
    scenario_id: str
    seed: int                        # derived from (date, airline, flight_number)
    fixture: bool = False            # True only for hand-made fixtures
    row: DotRow                      # REAL source row
    disruption_type: Literal["WEATHER", "LATE_AIRCRAFT"]
    disruption_min: int              # the qualifying delay minutes from the row
    origin: Airport
    destination: Airport
    disrupted: FlightRef
    bank: list[FlightRef]            # arrivals into destination, same date, sched_arr ±90 min (REAL)
    connections: list[FlightRef]     # same-airline departures from destination 30–150 min after sched arr (REAL; pax SYNTHETIC)
    base_eta_min: int                # sched_arr_min + arrival_delay: the ETA when eta_shift_min = 0
    aar_nominal: int                 # REAL_DERIVED: peak observed hourly arrivals that day
    aar_reduced: int                 # SYNTHETIC rule (config.thresholds.aar_weather_factor)
    aircraft_size: SizeClass         # SYNTHETIC
    fuel_at_fix_min: float           # SYNTHETIC: fuel on board at arrival fix, in minutes of flight
    flight_crew_duty_remaining_min: int   # SYNTHETIC
    ramp_shift_end_min: int          # SYNTHETIC
    next_departure_min: int | None   # REAL if the tail's next departure is found, else SYNTHETIC (see provenance)
    gates: list[Gate]
    taxiways: list[str]
    blocked_taxiways: list[str] = []
    turbulence_by_fp: dict[str, float]    # SYNTHETIC: FPAdj -> turbulence_idx in [0,1]
    chaos_applied: list[ChaosEvent] = []
    provenance: dict[str, Provenance]     # field name -> provenance, for EVERY field above except ids
    # --- v1.2 (organisers' workbook), all with defaults so v1.1 data still parses ---
    airport_limits: dict = {}        # destination's workbook row: {size_class, active_runways, gates, max_runway_ops_per_hour,
                                     #   min_turnaround_min, spare_gates_at_any_time}; provenance "synthetic" (organiser-provided)
    planned_gate: str | None = None  # SYNTHETIC: gate assigned before the disruption; any other gate is a gate change
    decision_time_min: int | None = None  # SYNTHETIC: when the plan is decided (aircraft at the arrival fix)

class Metrics(BaseModel):            # computed by core.metrics, never by an LLM
    eta_new_min: int
    runway_slot_min: int
    separation_margin_s: int         # gap to leader minus required wake separation (negative = violation)
    fuel_at_landing_min: float
    extra_fuel_min: float            # vs. as_filed at eta_shift 0
    hold_min: int
    turbulence_idx: float
    misconnected_pax: int
    gate: str
    gate_free_from_min: int
    gate_free_to_min: int
    taxi_path_ok: bool
    turnaround_buffer_min: int       # next_departure - (eta_new + taxi_in + min_turnaround)
    ramp_overtime_min: int
    bank_delay_added_min: int        # delay pushed onto other bank flights
    arrivals_this_hour: int
    throughput_loss: int             # max(0, arrivals_this_hour - aar_reduced) or slots lost
    cost_J: float                    # fallback weighted cost (config.fallback_weights)
    # --- v1.2 ---
    gate_change: bool = False                 # gate != scenario.planned_gate
    gate_change_notice_min: int | None = None # eta_new_min - decision_time_min when gate_change, else None (H4 needs >= 20)
    fuel_at_landing_kg: float | None = None   # fuel_at_landing_min x workbook burn rate (display only)

class Option(BaseModel):
    option_id: str
    eta_shift_min: int
    gate: str
    fp_adjustment: FPAdj
    source: Literal["generated", "counter", "fcfs"]
    proposed_by: AgentRole | None = None   # set for counters
    parent_option: str | None = None        # set for counters
    label: str                              # short human label, e.g. "+10 min, gate B2, speed reduction"
    metrics: Metrics

class ConstraintResult(BaseModel):
    option_id: str
    constraint_id: ConstraintId
    passed: bool
    value: float | None              # measured value (e.g. 27.5 fuel min)
    threshold: float | None          # rule threshold (e.g. 30)
    detail: str                      # <= 120 chars, e.g. "fuel 27.5 min < 30 min final reserve"

class CheckReport(BaseModel):
    option_id: str
    feasible: bool                   # all 7 passed
    results: list[ConstraintResult]  # always exactly 7, in H1..H7 order

class FallbackResult(BaseModel):
    status: Literal["PLAN", "ESCALATE"]
    option_id: str | None            # None iff ESCALATE
    cost_J: float | None
    ranking: list[tuple[str, float]] # feasible options sorted by J ascending
    weights: dict[str, float]
    reason: str                      # e.g. "min J among 5 feasible" / "no feasible option: diversion candidate"

class ScenarioSummary(BaseModel):    # list item for GET /api/scenarios
    scenario_id: str
    date: str                        # "2015-01-02"
    flight_id: str
    origin: str
    destination: str
    disruption_type: Literal["WEATHER", "LATE_AIRCRAFT"]
    disruption_min: int

class ScenarioBundle(BaseModel):     # everything the coordinator and the UI need for one scenario
    scenario: Scenario
    options: list[Option]            # 6–8 candidates (generated)
    checks: dict[str, CheckReport]   # option_id -> report, for every option incl. opt_fcfs
    fallback: FallbackResult         # B1, computed in shadow
    fcfs: Option                     # B0 baseline (option_id "opt_fcfs")
```

### 1.1 Core functions (W1 provides; signatures are the contract)

```python
# core/config.py
def load_config(path: str = "config.yaml") -> dict

# core/scenario.py
def list_scenarios(limit: int = 50, airport: str | None = None, date: str | None = None) -> list[ScenarioSummary]
def build_scenario(scenario_id: str) -> Scenario            # reads data/qualifying.parquet; seeded and reproducible

# core/metrics.py
def compute_metrics(s: Scenario, eta_shift_min: int, gate: str, fp: FPAdj) -> Metrics

# core/options.py
def make_option(s: Scenario, option_id: str, eta_shift_min: int, gate: str, fp: FPAdj,
                source: str = "generated", proposed_by: AgentRole | None = None,
                parent_option: str | None = None) -> Option
def generate_options(s: Scenario) -> list[Option]            # 6–8 Pareto-pruned candidates, ids opt_1..
def counter_allowed_values(s: Scenario) -> dict[str, list]   # {"eta_shift_min":[...], "gate":[...], "fp_adjustment":[...]}

# core/constraints.py
def check_option(s: Scenario, opt: Option) -> CheckReport
def check_all(s: Scenario, opts: list[Option]) -> dict[str, CheckReport]

# core/fallback.py
def fcfs(s: Scenario) -> Option                               # B0
def solve(s: Scenario, opts: list[Option], checks: dict[str, CheckReport],
          weights: dict | None = None) -> FallbackResult      # B1; weights default from config

# core/bundle.py
def build_bundle(scenario_id: str, chaos: list[ChaosEvent] | None = None) -> ScenarioBundle
def build_bundle_from_scenario(s: Scenario) -> ScenarioBundle

# core/chaos.py
def apply_chaos(s: Scenario, ev: ChaosEvent) -> Scenario     # returns a NEW scenario; appends to chaos_applied

# core/mapdata.py
def map_payload(s: Scenario) -> MapPayload                    # see §4.3

# core/log.py   (see §5)
class ConsensusLog:
    def __init__(self, run_id: str, scenario: Scenario, runs_dir: str = "runs"): ...
    def append(self, event_type: str, actor: str, payload: dict,
               constraint_ids: list[str] | None = None) -> LogEntry
    def entries(self) -> list[LogEntry]
    def head_hash(self) -> str
    @property
    def path(self) -> str                                     # runs/<run_id>.jsonl
def verify_chain(path: str) -> VerifyResult
```

---

## 2. Agent message types: `agents/schema.py` (W2 owns)

```python
from pydantic import BaseModel, Field
from typing import Literal

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
    rationale: str = Field(max_length=300)

def build_position_model(option_ids: list[str], metric_refs: list[str], round: int) -> type[BaseModel]
    # dynamic enums: OptionId and MetricRef restricted to this scenario; counter forbidden when round == MAX_ROUNDS
```

Round semantics: R1 action ∈ {PROPOSE, COUNTER}; R2 ∈ {ACCEPT, REJECT, COUNTER}; R3 ∈ {ACCEPT, REJECT} on the tentative option only.
In R2/R3, `ACCEPT` means "I accept the current tentative option".

```python
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
```

Coordinator entry point (W2):
```python
# agents/coordinator.py
class Coordinator:
    def __init__(self, bundle: ScenarioBundle, run_id: str, config: dict | None = None,
                 llm: "LLMClient | None" = None): ...
    async def run(self) -> AsyncIterator[dict]       # yields SSE envelopes (§3); also writes every one to ConsensusLog
    async def approve(self, action: Literal["APPROVE","OVERRIDE"], option_id: str, by: str, note: str = "") -> dict
# agents/killswitch.py
def set_llm_enabled(enabled: bool) -> None; def llm_enabled() -> bool   # process-global; checked before every LLM call
```
`LLMClient` must have a mock implementation (`agents/client.py: MockLLMClient`) usable with no API key, so the coordinator and the API run offline.

---

## 3. SSE events (coordinator → API → console)

Transport: `text/event-stream`. Each message is `event: <type>` + `data: <envelope JSON>`.

```json
{ "type": "agent_position", "run_id": "run_...", "seq": 7, "ts": "2026-10-31T03:41:07.123Z",
  "log_hash": "<sha256 hex of the log entry written for this event>", "data": { ... } }
```
`seq` starts at 0 and increases by 1 per run. `ts` is ISO-8601 UTC with milliseconds.

| `type` | `data` payload |
|---|---|
| `run_started` | `{scenario_id, max_rounds, llm_enabled, models: {ATC,PILOT,GROUND,NARRATOR}, parent_run_id: str\|null, chaos_applied: [ChaosEvent]}` |
| `options` | `{options: [Option], checks: {option_id: CheckReport}, fallback: FallbackResult, fcfs: Option}`. Sent after `run_started` and again whenever the option set changes (accepted counter, chaos) |
| `round_started` | `{round, phase: "PROPOSE"\|"RESPOND"\|"BALLOT", candidates: [option_id], tentative: option_id\|null}` |
| `agent_thinking` | `{round, agent}` (one per agent, just before the call) |
| `agent_position` | `AgentMessage` (§2) |
| `counter_checked` | `{round, agent, counter: Counter, accepted: bool, option_id: str\|null, reason: str, check: CheckReport\|null, failed: [ConstraintId]}`. `option_id` is the new `opt_cN` if accepted. Rejected if off-grid, duplicate, or fails a hard constraint. *(v1.1)* `check` is non-null whenever the counter reached the checker (accepted or not); null only for off-grid/duplicate. `failed` lists failed constraint IDs (`[]` if none or not checked) |
| `veto` | `{round, option_id, agents: [AgentRole], failed: [ConstraintId], reason}`. One or more agents accepted/ranked-first an option that fails the checker; the checker overrides |
| `tentative` | `{round, option_id: str\|null, agreement_set: [option_id], minmax_rank: {option_id: int}}`. Agreement set = ∩ acceptable ∩ hard-feasible |
| `round_ended` | `{round, all_accept: bool, actions: {ATC: action\|null, PILOT: ..., GROUND: ...}}` |
| `consensus` | `{round, option_id, plan: Option, check: CheckReport, accepts: {ATC: rationale, PILOT: rationale, GROUND: rationale}}` |
| `fallback` | `{reason: "NO_CONSENSUS"\|"LLM_KILLED"\|"LLM_ERROR"\|"NO_FEASIBLE", result: FallbackResult, plan: Option\|null}`. `result.status == "ESCALATE"` means no safe automated plan |
| `narration` | `{text}` (narrator summary, ≤ 120 words; optional/stretch) |
| `awaiting_approval` | `{decision_source: "CONSENSUS"\|"FALLBACK"\|"ESCALATE", option_id: str\|null, rounds_used: int}` |
| `approved` | `{action: "APPROVE"\|"OVERRIDE", option_id, by, note, final_hash}` (human sign-off closes the chain). *(v1.1)* `final_hash` = the log head hash **before** the approval entry (the chain being signed off). The envelope `log_hash` = the approval entry's own hash. |
| `run_ended` | `{final_state: "CONSENSUS"\|"FALLBACK"\|"ESCALATE"\|"SUPERSEDED", rounds_used, latency_ms, chain_ok: bool, n_llm_calls: int}`. *(v1.1)* `SUPERSEDED` = cancelled because a chaos event started a child run |
| `error` | `{message, fatal: bool}` |

Order of a normal run: `run_started, options, [round_started, agent_thinking×3, agent_position×3, counter_checked*, options?, veto*, tentative, round_ended]×≤3, consensus|fallback, narration?, awaiting_approval, run_ended`. `approved` arrives later (after `POST /approve`) on the same stream if it is still open; it is always written to the log.

*(v1.1)* **Agreement set and tentative (pinned).** A = ∩ over agents of acceptable ∩ hard-feasible, where an agent's acceptable set is its latest `acceptable` list, plus the tentative if its action is `ACCEPT`. A counter accepted in the current round is provisionally acceptable to its proposer and to every agent whose acceptable set contains its `parent_option`; from the next round on, agents' own lists decide. Rank of an option for an agent = its 1-based position in that agent's `ranking`, else its parent's position (for a counter), else `len(candidates) + 1`. Tentative = argmin over A of max rank across agents; ties by lower `metrics.cost_J`, then `option_id`.

*(v1.1)* **Seq.** Envelope `seq` counts SSE events only (from 0). Log `seq` counts log entries (seq 0 = `scenario_loaded`, which has no SSE event). They differ. Clients match events to log entries by `log_hash`, never by seq.

*(v1.1)* **Unsafe proposals blocked** (eval headline): `Σ len(veto.data.agents) + count(counter_checked where failed != [])`. W1 (eval) and W2 (coordinator) count exactly this.

Invariants the UI may rely on: at most 3 `round_started`; `round == 3` never has `counter_checked`; exactly one of `consensus`/`fallback` per run; every plan in `consensus`/`fallback` has `check.feasible == true` (or `fallback.result.status == "ESCALATE"` and `plan == null`).

---

## 4. HTTP API: `api/server.py` (W3 owns). Prefix `/api`. JSON unless stated.

| Method & path | Body | Response |
|---|---|---|
| `GET /api/health` | | `{ok: true, llm_enabled: bool, models: {...}, data_loaded: bool, mock: bool, llm_budget: LLMBudget}` *(v1.2: `llm_budget` added)* |
| `GET /api/limits` | | *(v1.2)* `{workbook: {wake_separation, fuel_and_crew, rules_of_play}, airport: <airport_limits of the current scenario or null>, deviations: [str]}` from `config.yaml` + `data/airport_limits.json`, for the "Challenge limits" panel |
| `GET /api/scenarios?limit=&airport=&date=` | | `[ScenarioSummary]` |
| `GET /api/scenarios/{scenario_id}` | | `{bundle: ScenarioBundle, map: MapPayload}` |
| `POST /api/runs` | `{scenario_id, chaos?: [ChaosEvent], parent_run_id?: str}` | `{run_id}` |
| `GET /api/runs/{run_id}/stream` | | SSE (§3). Replays from seq 0 if the run already started |
| `POST /api/runs/{run_id}/chaos` | `ChaosEvent` | `{run_id: <new run>, parent_run_id}`: re-negotiates on the mutated scenario as a NEW run. *(v1.1)* Child `chaos` = parent's `chaos_applied` + the new event (accumulates). If the parent is still negotiating, it is cancelled and ends with `run_ended.final_state = "SUPERSEDED"` |
| `GET /api/runs/{run_id}/bundle` | | *(v1.1)* `{bundle: ScenarioBundle, map: MapPayload}` for this run's own (possibly chaos-mutated) scenario. The UI uses this, not `/api/scenarios/{id}`, once a run exists |
| `POST /api/runs/{run_id}/approve` | `{action: "APPROVE"\|"OVERRIDE", option_id, by: str, note?: str}` | `{ok, final_hash}`. *(v1.1)* `final_hash` = same value as `approved.data.final_hash` (head before the approval entry). `409` before `awaiting_approval`. On ESCALATE only `OVERRIDE` with an explicit `option_id` is allowed. The UI uses this response (the stream may already be closed) |
| `POST /api/kill` | `{llm_enabled: bool}` | `{llm_enabled}` |
| `GET /api/runs/{run_id}/log` | | `application/x-ndjson` download of `runs/<run_id>.jsonl` |
| `GET /api/runs/{run_id}/verify` | | `VerifyResult` (§5) |
| `GET /api/runs/{run_id}/record` | | `text/markdown` Resolution Record (narrator or template) |
| `GET /api/eval` | | contents of `eval/results.json` (§6), or `404` if not run yet |
| `GET /api/replay/{name}/stream` | | SSE replay of `api/hero_cache/<name>.jsonl` (demo insurance; the UI shows a "REPLAY" badge) |

`MOCK=1` env var: the server serves `docs/fixtures/*` and replays `run_events.jsonl` with ~600 ms between events, so the UI works with no data and no key.

### 4.3 Map payload (`core/mapdata.py` builds it; W1)

```python
class MapAirport(BaseModel):
    iata: str; name: str; lat: float; lon: float
    role: Literal["origin", "destination", "other"]

class MapFlight(BaseModel):
    flight_id: str
    role: FlightRole                         # "disrupted" | "bank" | "connection"
    origin: str; destination: str
    origin_lat: float; origin_lon: float
    dest_lat: float; dest_lon: float
    sched_dep_min: int; sched_arr_min: int   # REAL
    est_arr_min: int | None                  # REAL for bank; for disrupted = base_eta_min (updated by the plan's eta_new_min in the UI)
    position_estimated: bool = True          # markers are interpolated along great-circle arcs, not real tracks

class MapPayload(BaseModel):
    focus_airport: str                       # destination IATA
    airports: list[MapAirport]               # every airport referenced by flights
    flights: list[MapFlight]
    now_min: int                             # sim clock for marker positions (= disrupted sched_arr_min - 30)
```
Bank flights whose origin is missing from `airports.csv` are dropped from the map payload (not from the scenario).

---

### 4.4 LLM budget *(v1.2)*: `agents/budget.py` (W2 owns)
```python
class LLMBudget(BaseModel):
    keys: dict[str, dict]   # key env name -> {used_today, cap, remaining, rpm_cap}; never the key itself
    enforce: bool
    resets_at: str          # ISO time of the next daily reset
def budget_status() -> LLMBudget
def reserve(key_name: str) -> bool   # called before EVERY real request incl. retries; False -> refuse (status "rate_limited")
```
Ledger file `runs/llm_budget.json` (gitignored), shared by all processes with a file lock. A refused call counts as REJECT, so the run falls back safely.

## 5. Consensus log: `core/log.py` (W1 owns)

File: `runs/<run_id>.jsonl`, append-only, one JSON object per line.

```python
class LogEntry(BaseModel):
    seq: int                         # 0-based
    ts: str                          # ISO-8601 UTC ms
    run_id: str
    scenario_id: str
    source_row: dict                 # {"date":"2015-01-02","airline":"AA","flight_number":1234}
    event_type: str                  # the SSE type (§3), plus "scenario_loaded" at seq 0
    actor: Literal["COORDINATOR", "ATC", "PILOT", "GROUND", "CHECKER", "FALLBACK", "HUMAN", "SYSTEM", "NARRATOR"]
    constraint_ids: list[str]        # constraints applied/failed in this event ([] if none)
    synthetic_fields: list[str]      # names of synthetic fields referenced (seq 0 lists all from provenance)
    payload: dict                    # the SSE data payload, verbatim
    prev_hash: str                   # "0"*64 for seq 0
    hash: str                        # sha256(prev_hash + canonical_json(entry without "hash")).hexdigest()

class VerifyResult(BaseModel):
    ok: bool; n_entries: int; head_hash: str; broken_at: int | None
```
`canonical_json(x) = json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
Seq 0 is always `scenario_loaded` with payload `{scenario: Scenario}`. The SSE envelope's `log_hash` equals the `hash` of the entry written for that event.

*(v1.1)* `ConsensusLog.__init__` writes seq 0 itself when the file doesn't exist; if `runs/<run_id>.jsonl` already exists it **resumes** from the existing head (never truncates), so `approve` works after `run_ended` and after a server restart. `append()` serialises the payload at call time (deep copy); mutating the caller's object afterwards must not change the entry. `verify_chain` hashes the raw `json.loads` dicts, never Pydantic re-dumps.

---

## 6. Eval output: `eval/results.json` (W1)

```json
{ "generated_at": "...", "n": 30, "n_dev": 5, "seed": 42,
  "status_quo": {"qualifying_flights": 0, "weather_delay_min": 0, "late_aircraft_delay_min": 0},
  "summary": {
    "consensus_rate": 0.0, "consensus_by_r2": 0.0, "consensus_by_r3": 0.0,
    "fallback_rate": 0.0, "escalate_rate": 0.0,
    "unsafe_proposals_blocked": 0, "unsafe_plans_executed": 0,
    "schema_failure_rate": 0.0, "retry_rate": 0.0,
    "latency_p50_ms": 0, "latency_p95_ms": 0, "tokens_per_resolution": 0,
    "J_mean": {"accord": 0.0, "B0_fcfs": 0.0, "B1_optimizer": 0.0},
    "regret_vs_B1_mean": 0.0,
    "vs_B0": {"bank_delay_added_min": 0.0, "misconnected_pax": 0.0, "ramp_overtime_min": 0.0}
  },
  "ablations": {"B2_single_agent": null, "B3_model": null},
  "per_scenario": [ {"scenario_id": "...", "final_state": "CONSENSUS", "rounds_used": 2, "option_id": "opt_3",
                     "J": 0.0, "J_B0": 0.0, "J_B1": 0.0, "unsafe_blocked": 0, "latency_ms": 0, "run_id": "..."} ],
  "measured": true }
```
Every number is measured from runs. If a field was not run, it is `null`, never estimated.

---

## Changelog
- v1.0 (11:20): initial freeze.
- v1.2.3 (15:05), additive (updated brief: "pick any row of flights.csv"): `core.scenario.scenario_id_for_row(row)` (0-based data row, file order; W1-09); `GET /api/scenarios/by_row/{row}` → `ScenarioSummary + row` (404 out of range, 422 non-qualifying), `GET /api/scenarios/{id}/csv_row` → `{row}`; default `GET /api/scenarios` prepends the heroes with `hero: true`; UI `?scenario=<id>`. Airports with no coordinates build with a 0.0 placeholder, provenance `synthetic`; the map drops them (W3-07).
- v1.2.2 (13:58), additive, documents what `eval/run_eval.py` already writes (W1-07/W1-08a): `eval/results.json` top level gains `llm: "none"|"mock"|"live"`, `shard`, `eval_set_sha256` (must equal the hash of `eval/eval_set.json`); `summary` gains `llm`, `n_errors`, `regret_vs_B1_mean`, `vs_B0 {bank_delay_added_min, misconnected_pax, ramp_overtime_min}`, `B1_escalate_rate`, `B0_infeasible_rate`; `bad_day` gains `label`, `choice`, `n_skipped`, `skipped`, `B0_on_B1_planned` (B0 totals restricted to rows where B1 has a feasible plan; the fair comparison), `notes`, `generated_at`. Consumers must show `llm: "mock"` as SCRIPTED and `"none"` as baselines only; only `"live"` is an LLM result. `summary` also gains `ungrounded_rate` = positions with `ungrounded: true` / all ok positions (null when llm != live) (W2-05 grounding check). Option generator: keeps the cheapest feasible gate per (shift, fp) plus the planned gate; min-J is always offered.
- v1.2.1 (13:15), additive: optional `Metrics.gate_wait_min: int = 0` (W1-07, only if used); `eval/results.json` gains `bad_day: {airport, date, n_flights, B0, B1, b0_infeasible, b1_escalate} | null` (deterministic baselines only); `eval/eval_set.json` is the frozen held-out set.
- v1.2 (12:55): organisers' workbook adopted (human decision). Additive fields `Scenario.airport_limits/planned_gate/decision_time_min`, `Metrics.gate_change/gate_change_notice_min/fuel_at_landing_kg`; H4 includes the 20-min gate-change notice; H5 = flight crew 13 h duty only (ramp overtime is a cost); `GET /api/limits`; `/health.llm_budget`; §4.4 LLM budget guard.
- v1.1 (12:25), from REVIEWER-00, all additive: unpadded flight ids; provenance key convention and required keys; `counter_checked.failed` and non-null `check`; `approved.final_hash` = pre-approval head; `SUPERSEDED` final state; agreement-set/rank/tie rules pinned (W2's implementation); seq vs log seq; unsafe-blocked definition; `GET /api/runs/{id}/bundle`; chaos accumulates and supersedes the parent; approve 409/ESCALATE rules; log constructor writes seq 0 and resumes; `append` deep-copies. Fixtures regenerated to match.
