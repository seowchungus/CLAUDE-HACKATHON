"""Scenario builder (proposal §2.2): one real DOT row + real context, then seeded synthetic fields.

Real first: the row, arrival bank (arrivals into DEST same date, sched_arr within ±bank_window_min),
connections (same-airline departures from DEST 30-150 min after sched arr; at most MAX_CONNECTIONS, those
still catchable first), the tail's next departure.
Organisers' workbook [WB] (data/airport_limits.json, synthetic by the organisers): airport_limits, aar_nominal
(= max_runway_ops_per_hour x arrival_share_of_runway_ops), spare gates, turnaround, fuel spare, duty, shift.
Synthetic second, all from random.Random(seed): wake, aircraft size, fuel, crew, ramp shift, pax, turbulence,
gate template. Every synthetic field is listed as "synthetic" in Scenario.provenance.

Data note: data/raw/flights.csv as supplied is pre-filtered to qualifying rows only, so banks, connections and
AAR are computed from delayed flights only (an undercount of real traffic).
"""
import csv
import functools
import hashlib
import random

import polars as pl

from core.config import load_config, repo_path
from core.metrics import PLANNED_BURN_FIX_TO_LAND
from core.types import Airport, DotRow, FlightRef, Gate, Scenario, ScenarioSummary

MAX_CONNECTIONS = 8
DEFAULT_TAXI_IN = 8
FP_LIST = ["as_filed", "speed_reduction", "hold_10", "hold_20", "reroute_weather"]


# ---------- data access (cached)

@functools.lru_cache(maxsize=1)
def _qualifying() -> pl.DataFrame:
    return pl.read_parquet(repo_path(load_config()["paths"]["qualifying"]))


@functools.lru_cache(maxsize=1)
def _index() -> pl.DataFrame:
    return pl.read_parquet(repo_path("data/arrivals_index.parquet"))


@functools.lru_cache(maxsize=64)
def _index_day(date: str) -> pl.DataFrame:
    return _index().filter(pl.col("DATE") == date)


@functools.lru_cache(maxsize=1)
def airports() -> dict[str, Airport]:
    out: dict[str, Airport] = {}
    path = repo_path(f"{load_config()['paths']['raw_dir']}/airports.csv")
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out[r["IATA_CODE"]] = Airport(iata=r["IATA_CODE"], name=r["AIRPORT"], city=r["CITY"],
                                              state=r["STATE"], lat=float(r["LATITUDE"]),
                                              lon=float(r["LONGITUDE"]))
            except (ValueError, TypeError):
                continue  # a few airports have no coordinates
    return out


@functools.lru_cache(maxsize=1)
def _workbook() -> dict:
    import json
    with open(repo_path(load_config()["workbook"]["extracted"])) as f:
        return json.load(f)


def airport_limits(iata: str) -> dict:
    """[WB] airport_capacity row for iata; airports missing from the workbook get workbook.default_size_class."""
    wb = _workbook()
    if iata in wb["airports"]:
        return dict(wb["airports"][iata])
    return dict(wb["defaults_by_size_class"][load_config()["workbook"]["default_size_class"]])


@functools.lru_cache(maxsize=1)
@functools.lru_cache(maxsize=1)
def _airports_without_coords() -> dict[str, Airport]:
    """airports.csv rows with no LATITUDE/LONGITUDE (e.g. ECP): name/city/state are real, lat/lon are a 0.0
    placeholder. They build scenarios; the map drops them (core.mapdata only uses airports())."""
    out: dict[str, Airport] = {}
    with open(repo_path(f"{load_config()['paths']['raw_dir']}/airports.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["IATA_CODE"] not in airports():
                out[r["IATA_CODE"]] = Airport(iata=r["IATA_CODE"], name=r["AIRPORT"], city=r["CITY"],
                                              state=r["STATE"], lat=0.0, lon=0.0)
    return out


@functools.lru_cache(maxsize=1)
def _raw_keys() -> pl.DataFrame:
    """Key columns of data/raw/flights.csv in file order (row i here is data row i of the CSV, 0-based)."""
    path = repo_path(load_config()["paths"]["raw_dir"] + "/flights.csv")
    return pl.read_csv(path, columns=["YEAR", "MONTH", "DAY", "AIRLINE", "FLIGHT_NUMBER", "ORIGIN_AIRPORT",
                                      "DESTINATION_AIRPORT"],
                       schema_overrides={"AIRLINE": pl.Utf8, "ORIGIN_AIRPORT": pl.Utf8,
                                         "DESTINATION_AIRPORT": pl.Utf8})


def scenario_id_for_row(row: int) -> str:
    """The scenario_id for 0-based data row `row` of data/raw/flights.csv (file order, header excluded), which
    build_scenario / build_bundle accept. IndexError if out of range."""
    df = _raw_keys()
    if not 0 <= row < df.height:
        raise IndexError(f"row {row} out of range 0..{df.height - 1}")
    y, m, d, airline, fn, o, dest = df.row(row)
    return make_scenario_id(f"{y}-{m:02d}-{d:02d}", airline, fn, o, dest)


def dev_scenario_ids() -> list[str]:
    import json
    try:
        with open(repo_path("data/dev_rows.json")) as f:
            return list(json.load(f)["scenario_ids"])
    except FileNotFoundError:
        return []


# ---------- helpers

def hhmm_to_min(hhmm: int | None) -> int:
    if hhmm is None:
        return 0
    return (int(hhmm) // 100) * 60 + int(hhmm) % 100


def arr_minutes(sched_dep_hhmm: int, sched_arr_hhmm: int) -> int:
    """Scheduled arrival in minutes after midnight of the flight date; +1440 for overnight arrivals."""
    dep, arr = hhmm_to_min(sched_dep_hhmm), hhmm_to_min(sched_arr_hhmm)
    return arr + 1440 if arr < dep - 240 else arr


def make_seed(date: str, airline: str, flight_number: int) -> int:
    return int(hashlib.sha256(f"{date}|{airline}|{int(flight_number)}".encode()).hexdigest()[:8], 16)


def make_scenario_id(date: str, airline: str, flight_number: int, origin: str, dest: str) -> str:
    return f"{date}_{airline}{int(flight_number)}_{origin}-{dest}"


def parse_scenario_id(scenario_id: str) -> tuple[str, str, int, str, str]:
    date, flight, route = scenario_id.split("_")
    origin, dest = route.split("-")
    return date, flight[:2], int(flight[2:]), origin, dest


def _f(x) -> float | None:
    return None if x is None else float(x)


def _wake(rng: random.Random, distance: int | None) -> str:
    d = distance or 800
    r = rng.random()
    if d > 2000:
        return "H" if r < 0.5 else "M"
    if d > 1000:
        return "H" if r < 0.15 else "M"
    if d < 400:
        return "L" if r < 0.3 else "M"
    return "L" if r < 0.05 else "M"


def _aircraft_size(rng: random.Random, wake: str, distance: int) -> str:
    if wake == "H":
        return "L"
    if wake == "L":
        return "S"
    return "L" if (distance > 1500 and rng.random() < 0.4) else "M"


# ---------- public API

def list_scenarios(limit: int = 50, airport: str | None = None, date: str | None = None) -> list[ScenarioSummary]:
    q = _qualifying()
    if airport:
        q = q.filter(pl.col("DESTINATION_AIRPORT") == airport.upper())
    if date:
        q = q.filter(pl.col("DATE") == date)
    known = set(airports())
    q = q.filter(pl.col("ORIGIN_AIRPORT").is_in(list(known)) & pl.col("DESTINATION_AIRPORT").is_in(list(known)))
    q = q.sort(["DATE", "SCHEDULED_ARRIVAL", "AIRLINE", "FLIGHT_NUMBER"])
    out: list[ScenarioSummary] = []
    seen: set[str] = set()
    if not airport and not date:  # dev rows first so the demo list starts with known-good scenarios
        for sid in dev_scenario_ids():
            try:
                out.append(_summary(_find_row(sid)))
                seen.add(sid)
            except KeyError:
                pass
    for r in q.head(limit + len(seen)).iter_rows(named=True):
        sm = _summary(r)
        if sm.scenario_id not in seen:
            out.append(sm)
            seen.add(sm.scenario_id)
    return out[:limit]


def _summary(r: dict) -> ScenarioSummary:
    dtype, dmin = _disruption(r)
    return ScenarioSummary(
        scenario_id=make_scenario_id(r["DATE"], r["AIRLINE"], r["FLIGHT_NUMBER"], r["ORIGIN_AIRPORT"],
                                     r["DESTINATION_AIRPORT"]),
        date=r["DATE"], flight_id=f"{r['AIRLINE']}{int(r['FLIGHT_NUMBER'])}", origin=r["ORIGIN_AIRPORT"],
        destination=r["DESTINATION_AIRPORT"], disruption_type=dtype, disruption_min=dmin)


def _disruption(r: dict) -> tuple[str, int]:
    w = r.get("WEATHER_DELAY") or 0
    la = r.get("LATE_AIRCRAFT_DELAY") or 0
    if w > 15 and (w >= la or la <= 20):
        return "WEATHER", int(w)
    return "LATE_AIRCRAFT", int(la)


def _find_row(scenario_id: str) -> dict:
    date, airline, fn, origin, dest = parse_scenario_id(scenario_id)
    q = _qualifying().filter((pl.col("DATE") == date) & (pl.col("AIRLINE") == airline)
                             & (pl.col("FLIGHT_NUMBER") == fn) & (pl.col("ORIGIN_AIRPORT") == origin)
                             & (pl.col("DESTINATION_AIRPORT") == dest)).sort("SCHEDULED_DEPARTURE")
    if q.height == 0:
        raise KeyError(f"no qualifying row for {scenario_id}")
    return q.row(0, named=True)


def build_scenario(scenario_id: str) -> Scenario:
    cfg = load_config()
    sc_cfg, th = cfg["scenario"], cfg["thresholds"]
    r = _find_row(scenario_id)
    date, airline, fn = r["DATE"], r["AIRLINE"], int(r["FLIGHT_NUMBER"])
    origin, dest = r["ORIGIN_AIRPORT"], r["DESTINATION_AIRPORT"]
    sid = make_scenario_id(date, airline, fn, origin, dest)
    seed = make_seed(date, airline, fn)
    rng = random.Random(seed)
    aps = {**_airports_without_coords(), **airports()}
    if origin not in aps or dest not in aps:
        raise KeyError(f"airport {origin if origin not in aps else dest} is not in airports.csv")
    no_coords = {c for c in (origin, dest) if c in _airports_without_coords()}

    row = DotRow(
        year=r["YEAR"], month=r["MONTH"], day=r["DAY"], airline=airline, flight_number=fn,
        tail_number=r["TAIL_NUMBER"], origin=origin, destination=dest,
        scheduled_departure=r["SCHEDULED_DEPARTURE"], departure_delay=_f(r["DEPARTURE_DELAY"]),
        scheduled_arrival=r["SCHEDULED_ARRIVAL"], arrival_delay=_f(r["ARRIVAL_DELAY"]),
        distance=int(r["DISTANCE"]), scheduled_time=_f(r["SCHEDULED_TIME"]), air_time=_f(r["AIR_TIME"]),
        taxi_in=_f(r["TAXI_IN"]), taxi_out=_f(r["TAXI_OUT"]), weather_delay=_f(r["WEATHER_DELAY"]),
        late_aircraft_delay=_f(r["LATE_AIRCRAFT_DELAY"]), air_system_delay=_f(r["AIR_SYSTEM_DELAY"]))
    dtype, dmin = _disruption(r)

    sched_dep = hhmm_to_min(row.scheduled_departure)
    sched_arr = arr_minutes(row.scheduled_departure, row.scheduled_arrival)
    base_eta = sched_arr + int(round(row.arrival_delay or 0))
    taxi_in = int(row.taxi_in or DEFAULT_TAXI_IN)

    # synthetic draws happen in a fixed order so the scenario is reproducible
    d_wake = _wake(rng, row.distance)
    disrupted = FlightRef(flight_id=f"{airline}{fn}", airline=airline, flight_number=fn,
                          tail_number=row.tail_number, origin=origin, destination=dest,
                          sched_dep_min=sched_dep, sched_arr_min=sched_arr, est_arr_min=base_eta,
                          role="disrupted", wake=d_wake)

    day = _index_day(date)
    arrivals = day.filter(pl.col("DESTINATION_AIRPORT") == dest).sort(
        ["SCHEDULED_ARRIVAL", "AIRLINE", "FLIGHT_NUMBER"])
    bank: list[FlightRef] = []
    win = sc_cfg["bank_window_min"]
    for b in arrivals.iter_rows(named=True):
        b_arr = arr_minutes(b["SCHEDULED_DEPARTURE"], b["SCHEDULED_ARRIVAL"])
        b_est = b_arr + int(b["ARRIVAL_DELAY"] or 0)
        if b["AIRLINE"] == airline and int(b["FLIGHT_NUMBER"]) == fn and b["ORIGIN_AIRPORT"] == origin:
            continue
        if abs(b_arr - sched_arr) <= win:
            bank.append(FlightRef(
                flight_id=f"{b['AIRLINE']}{int(b['FLIGHT_NUMBER'])}", airline=b["AIRLINE"],
                flight_number=int(b["FLIGHT_NUMBER"]), tail_number=b["TAIL_NUMBER"],
                origin=b["ORIGIN_AIRPORT"], destination=dest, sched_dep_min=hhmm_to_min(b["SCHEDULED_DEPARTURE"]),
                sched_arr_min=b_arr, est_arr_min=b_est, role="bank", wake=_wake(rng, b["DISTANCE"])))
    limits = airport_limits(dest)
    aar_nominal = max(1, round(limits["max_runway_ops_per_hour"] * th["arrival_share_of_runway_ops"]))

    lo, hi = sc_cfg["connection_window_min"]
    deps = day.filter((pl.col("ORIGIN_AIRPORT") == dest) & (pl.col("AIRLINE") == airline)).sort(
        ["SCHEDULED_DEPARTURE", "FLIGHT_NUMBER"])
    next_dep_real: int | None = None
    window: list[dict] = []
    for c in deps.iter_rows(named=True):
        c_dep = hhmm_to_min(c["SCHEDULED_DEPARTURE"])
        if (next_dep_real is None and row.tail_number and c["TAIL_NUMBER"] == row.tail_number
                and c_dep > sched_arr):
            next_dep_real = c_dep
        if lo <= c_dep - sched_arr <= hi:
            window.append(c)
    # keep at most MAX_CONNECTIONS, preferring those still catchable at eta_shift 0 (dep >= in-block + 45 min MCT)
    in_block0 = base_eta + taxi_in
    window.sort(key=lambda c: (hhmm_to_min(c["SCHEDULED_DEPARTURE"]) < in_block0 + 45,
                               hhmm_to_min(c["SCHEDULED_DEPARTURE"]), c["FLIGHT_NUMBER"]))
    connections: list[FlightRef] = []
    for c in sorted(window[:MAX_CONNECTIONS], key=lambda c: (c["SCHEDULED_DEPARTURE"], c["FLIGHT_NUMBER"])):
        connections.append(FlightRef(
            flight_id=f"{c['AIRLINE']}{int(c['FLIGHT_NUMBER'])}", airline=c["AIRLINE"],
            flight_number=int(c["FLIGHT_NUMBER"]), tail_number=c["TAIL_NUMBER"], origin=dest,
            destination=c["DESTINATION_AIRPORT"], sched_dep_min=hhmm_to_min(c["SCHEDULED_DEPARTURE"]),
            sched_arr_min=arr_minutes(c["SCHEDULED_DEPARTURE"], c["SCHEDULED_ARRIVAL"]),
            est_arr_min=None, role="connection", wake=_wake(rng, c["DISTANCE"]),
            pax_connecting=rng.randint(3, 25)))

    wd = row.weather_delay or 0
    if dtype == "WEATHER" or wd > 15:
        band = "light" if wd <= 30 else ("moderate" if wd <= 60 else "severe")
        factor = th["aar_weather_factor"][band]
    else:
        factor = 1.0
    aar_reduced = max(1, round(aar_nominal * factor))

    aircraft_size = _aircraft_size(rng, d_wake, row.distance)
    # [WB] landing as filed at +0 leaves the assumed 45 min spare holding fuel (15 min above final reserve)
    fuel_at_fix = float(th["fuel_spare_on_arrival_min"]) + PLANNED_BURN_FIX_TO_LAND
    # [WB] 13 h duty from report time; duty already used is seeded: 60 min report + prior legs + this leg
    n_prior = rng.choices([0, 1, 2, 3], weights=[30, 35, 25, 10])[0]
    prior = sum(rng.randint(70, 180) + 40 for _ in range(n_prior))
    used = 60 + prior + int(row.scheduled_time or 120) + int(max(0, row.departure_delay or 0))
    # floor: a crew already out of duty would not be dispatched; 10-40 min left makes duty bind on larger shifts
    crew_duty = max(rng.randint(10, 40), th["flight_crew_max_duty_min"] - used)
    in_block = base_eta + taxi_in
    # [WB] 8 h ground shift with a seeded start, so it ends within about an hour of our in-block time
    shift_start = in_block + 30 + rng.randint(-20, 40) - th["ground_shift_min"]
    ramp_shift_end = shift_start + th["ground_shift_min"]
    turnaround = limits["min_turnaround_min"]
    if next_dep_real is not None:
        next_departure, nd_prov = next_dep_real, "real"
    else:
        next_departure, nd_prov = in_block + turnaround + rng.randint(5, 50), "synthetic"
    decision_time = base_eta - rng.randint(15, 25)

    sev = min(1.0, wd / 90.0)
    t0 = 0.2 + 0.5 * sev + rng.uniform(-0.08, 0.12)
    turb = {"as_filed": t0, "speed_reduction": t0 - 0.04, "hold_10": t0 - 0.06, "hold_20": t0 - 0.08,
            "reroute_weather": t0 * 0.35}
    turbulence_by_fp = {k: round(min(1.0, max(0.0, v)), 2) for k, v in turb.items()}

    taxiways = list(sc_cfg["taxiways"])
    gates, planned_gate = _gate_template(rng, sc_cfg["gates_per_airport"], taxiways, in_block,
                                         limits["spare_gates_at_any_time"], aircraft_size)

    provenance = {
        "row": "real", "disruption_type": "real", "disruption_min": "real", "origin": "real",
        "destination": "real", "disrupted": "real", "bank": "real", "connections": "real",
        "base_eta_min": "real", "aar_nominal": "synthetic", "aar_reduced": "synthetic",
        "aircraft_size": "synthetic", "fuel_at_fix_min": "synthetic",
        "flight_crew_duty_remaining_min": "synthetic", "ramp_shift_end_min": "synthetic",
        "next_departure_min": nd_prov, "gates": "synthetic", "taxiways": "synthetic",
        "blocked_taxiways": "synthetic", "turbulence_by_fp": "synthetic", "chaos_applied": "synthetic",
        "disrupted.wake": "synthetic", "bank.wake": "synthetic", "connections.wake": "synthetic",
        "connections.pax_connecting": "synthetic",
        "airport_limits": "synthetic", "planned_gate": "synthetic", "decision_time_min": "synthetic",
    }
    if origin in no_coords:
        provenance["origin"] = "synthetic"  # lat/lon placeholder 0.0 (airports.csv has none); map drops it
    if dest in no_coords:
        provenance["destination"] = "synthetic"
    return Scenario(
        scenario_id=sid, seed=seed, row=row, disruption_type=dtype, disruption_min=dmin,
        origin=aps[origin], destination=aps[dest], disrupted=disrupted, bank=bank, connections=connections,
        base_eta_min=base_eta, aar_nominal=aar_nominal, aar_reduced=aar_reduced, aircraft_size=aircraft_size,
        fuel_at_fix_min=fuel_at_fix, flight_crew_duty_remaining_min=crew_duty,
        ramp_shift_end_min=ramp_shift_end, next_departure_min=next_departure, gates=gates, taxiways=taxiways,
        turbulence_by_fp=turbulence_by_fp, provenance=provenance, airport_limits=limits,
        planned_gate=planned_gate, decision_time_min=decision_time)


def _gate_template(rng: random.Random, n: int, taxiways: list[str], in_block: int, n_spare: int,
                   aircraft_size: str) -> tuple[list[Gate], str]:
    """n gates near the flight (3 concourses; A via taxiway A, B via B/C, C via C/D). [WB] exactly n_spare
    gates are free around the ETA; the rest are occupied at in-block, some freeing 5-90 min later (tight).
    The planned gate (pre-disruption assignment) is busy at in-block in ~65% of rows and frees 5-25 min later,
    forcing a later slot, a ramp wait or a gate change; otherwise it is a spare gate that is taken again 125-160 min after in-block."""
    concourses = ["A", "B", "C"]
    per = max(1, n // len(concourses))
    sizes = {"A": ["L", "L", "M", "M"], "B": ["L", "M", "M", "S"], "C": ["M", "M", "S", "S"]}
    paths = {"A": [["A"], ["A"], ["A", "B"], ["A", "B"]],
             "B": [["B"], ["B"], ["B", "C"], ["B", "C"]],
             "C": [["C"], ["C", "D"], ["D"], ["D"]]}
    rank = {"S": 0, "M": 1, "L": 2}
    specs = [(f"{c}{i + 1}", c, sizes[c][i % 4], [t for t in paths[c][i % 4] if t in taxiways] or taxiways[:1])
             for c in concourses for i in range(per)]
    ids = [x[0] for x in specs]
    fits = [x[0] for x in specs if rank[x[2]] >= rank[aircraft_size]]
    spare = set(rng.sample(ids, min(n_spare, len(ids))))
    if not spare & set(fits):  # at least one spare gate must fit the aircraft
        spare.pop()
        spare.add(rng.choice(fits))
    busy_fits = [g for g in fits if g not in spare]
    if busy_fits and rng.random() < 0.65:
        planned, planned_busy = rng.choice(busy_fits), True
    else:
        planned, planned_busy = rng.choice(sorted(spare & set(fits))), False
    gates: list[Gate] = []
    for gid, c, size, path in specs:
        if gid == planned and planned_busy:
            occ = [(in_block - rng.randint(30, 90), in_block + rng.randint(5, 25))]  # frees inside the shift grid
        elif gid == planned:
            st = in_block + rng.randint(125, 160)  # free for the whole gate hold, taken again afterwards
            occ = [(st, st + rng.randint(40, 90))]
        elif gid in spare:
            occ = []
        else:
            occ = [(in_block - rng.randint(30, 90), in_block + rng.randint(5, 90))]
        gates.append(Gate(gate_id=gid, concourse=c, size=size, taxi_path=path, occupied=occ))
    return gates, planned
