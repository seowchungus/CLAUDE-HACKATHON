"""Core types. Transcribed from docs/CONTRACTS.md v1.2 (§1, §4.3, §5). Do not rename fields."""
from typing import Literal

from pydantic import BaseModel, Field  # noqa: F401  (Field re-exported for contract parity)

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

CONSTRAINT_IDS: list[str] = ["H1_wake_separation", "H2_runway_capacity", "H3_fuel_reserve",
                             "H4_gate_validity", "H5_crew_duty", "H6_taxiway_reachability",
                             "H7_severe_turbulence"]
FP_ADJUSTMENTS: list[str] = ["as_filed", "speed_reduction", "hold_10", "hold_20", "reroute_weather"]


class DotRow(BaseModel):            # verbatim from flights.csv (REAL). Times are raw HHMM ints as in the CSV.
    year: int
    month: int
    day: int
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
    iata: str
    name: str
    city: str
    state: str
    lat: float
    lon: float


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
    # --- v1.2.1 ---
    gate_wait_min: int = 0                    # ramp wait for the chosen gate to free up (adds to in-block time)


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


# ---- §4.3 map payload

class MapAirport(BaseModel):
    iata: str
    name: str
    lat: float
    lon: float
    role: Literal["origin", "destination", "other"]


class MapFlight(BaseModel):
    flight_id: str
    role: FlightRole                         # "disrupted" | "bank" | "connection"
    origin: str
    destination: str
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    sched_dep_min: int                       # REAL
    sched_arr_min: int                       # REAL
    est_arr_min: int | None                  # REAL for bank; for disrupted = base_eta_min (updated by the plan's eta_new_min in the UI)
    position_estimated: bool = True          # markers are interpolated along great-circle arcs, not real tracks


class MapPayload(BaseModel):
    focus_airport: str                       # destination IATA
    airports: list[MapAirport]               # every airport referenced by flights
    flights: list[MapFlight]
    now_min: int                             # sim clock for marker positions (= disrupted sched_arr_min - 30)


# ---- §5 consensus log

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
    ok: bool
    n_entries: int
    head_hash: str
    broken_at: int | None
