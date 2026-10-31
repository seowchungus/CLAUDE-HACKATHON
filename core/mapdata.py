"""Map payload (CONTRACTS.md §4.3). Coordinates are REAL (airports.csv); marker positions are estimated."""
from core.scenario import airports
from core.types import MapAirport, MapFlight, MapPayload, Scenario


def map_payload(s: Scenario) -> MapPayload:
    aps = airports()
    flights: list[MapFlight] = []
    used: set[str] = set()
    for f in [s.disrupted] + s.bank + s.connections:
        o, d = aps.get(f.origin), aps.get(f.destination)
        if o is None or d is None:
            continue  # dropped from the map only, not from the scenario
        est = s.base_eta_min if f.role == "disrupted" else f.est_arr_min
        flights.append(MapFlight(flight_id=f.flight_id, role=f.role, origin=f.origin, destination=f.destination,
                                 origin_lat=o.lat, origin_lon=o.lon, dest_lat=d.lat, dest_lon=d.lon,
                                 sched_dep_min=f.sched_dep_min, sched_arr_min=f.sched_arr_min, est_arr_min=est))
        used.update((f.origin, f.destination))
    role = {s.origin.iata: "origin", s.destination.iata: "destination"}
    airport_list = [MapAirport(iata=c, name=aps[c].name, lat=aps[c].lat, lon=aps[c].lon, role=role.get(c, "other"))
                    for c in sorted(used)]
    return MapPayload(focus_airport=s.destination.iata, airports=airport_list, flights=flights,
                      now_min=s.disrupted.sched_arr_min - 30)
