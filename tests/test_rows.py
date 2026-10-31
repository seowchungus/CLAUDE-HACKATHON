import random

import polars as pl
import pytest

from core.bundle import build_bundle
from core.mapdata import map_payload
from core.scenario import _raw_keys, airports, scenario_id_for_row


def test_scenario_id_for_row_matches_csv_order_and_bounds():
    n = _raw_keys().height
    assert n == 358774
    assert scenario_id_for_row(0) == "2015-01-01_AA5_DFW-HNL"
    assert scenario_id_for_row(n - 1) == "2015-12-31_WN5629_RDU-BNA"
    for bad in (-1, n):
        with pytest.raises(IndexError):
            scenario_id_for_row(bad)


def test_any_row_builds_incl_first_last_random_and_airports_without_coordinates():
    n = _raw_keys().height
    known = set(airports())
    no_coords = (_raw_keys().with_row_index("i")
                 .filter(~pl.col("ORIGIN_AIRPORT").is_in(known) | ~pl.col("DESTINATION_AIRPORT").is_in(known))["i"]
                 .to_list())
    rows = [0, n - 1] + random.Random(7).sample(range(n), 8) + no_coords[:2] + no_coords[-1:]
    for i in rows:
        b = build_bundle(scenario_id_for_row(i))
        assert b.fallback.status in ("PLAN", "ESCALATE") and len(b.options) >= 6, i
        map_payload(b.scenario)  # a coordinate-less airport is dropped from the map, never a crash
    s = build_bundle(scenario_id_for_row(no_coords[0])).scenario
    assert "synthetic" in (s.provenance["origin"], s.provenance["destination"])
