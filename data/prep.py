"""One-off data prep (proposal §2.1). Run from repo root: python data/prep.py

Writes:
  data/qualifying.parquet     rows with WEATHER_DELAY > 15 OR LATE_AIRCRAFT_DELAY > 20, not cancelled/diverted
  data/arrivals_index.parquet all non-cancelled flights, narrow columns (banks, connections, next-tail departures)
  data/status_quo.json        computed status-quo cost over the qualifying rows
Rows whose ORIGIN/DEST are not 3-letter alphabetic IATA codes (October numeric-ID quirk) are dropped and counted.
"""
import json
import os
import sys

import polars as pl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import load_config, repo_path  # noqa: E402

IATA_RE = r"^[A-Z]{3}$"
STR_COLS = {"AIRLINE": pl.Utf8, "TAIL_NUMBER": pl.Utf8, "ORIGIN_AIRPORT": pl.Utf8,
            "DESTINATION_AIRPORT": pl.Utf8, "CANCELLATION_REASON": pl.Utf8}
INDEX_COLS = ["DATE", "AIRLINE", "FLIGHT_NUMBER", "TAIL_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT",
              "SCHEDULED_DEPARTURE", "SCHEDULED_ARRIVAL", "ARRIVAL_DELAY", "DEPARTURE_DELAY", "DISTANCE"]


def main() -> None:
    cfg = load_config()
    raw = repo_path(os.path.join(cfg["paths"]["raw_dir"], "flights.csv"))
    lf = pl.scan_csv(raw, schema_overrides=STR_COLS, infer_schema_length=100_000)
    lf = lf.with_columns(
        pl.format("{}-{}-{}", pl.col("YEAR"), pl.col("MONTH").cast(pl.Utf8).str.zfill(2),
                  pl.col("DAY").cast(pl.Utf8).str.zfill(2)).alias("DATE"))

    n_raw = lf.select(pl.len()).collect().item()
    codes_ok = (pl.col("ORIGIN_AIRPORT").str.contains(IATA_RE) & pl.col("DESTINATION_AIRPORT").str.contains(IATA_RE))
    n_numeric = lf.filter(~codes_ok).select(pl.len()).collect().item()
    clean = lf.filter(codes_ok)

    qual = clean.filter(
        ((pl.col("WEATHER_DELAY") > 15) | (pl.col("LATE_AIRCRAFT_DELAY") > 20))
        & (pl.col("CANCELLED") == 0) & (pl.col("DIVERTED") == 0)
    ).collect()
    qual.write_parquet(repo_path(cfg["paths"]["qualifying"]))

    idx = clean.filter(pl.col("CANCELLED") == 0).select(INDEX_COLS).collect()
    idx.write_parquet(repo_path("data/arrivals_index.parquet"))

    sq = {
        "qualifying_flights": qual.height,
        "weather_delay_min": int(qual["WEATHER_DELAY"].fill_null(0).sum()),
        "late_aircraft_delay_min": int(qual["LATE_AIRCRAFT_DELAY"].fill_null(0).sum()),
        "raw_rows": n_raw,
        "dropped_numeric_codes": n_numeric,
        "source": "data/raw/flights.csv (US DOT 2015), computed by data/prep.py",
    }
    with open(repo_path("data/status_quo.json"), "w") as f:
        json.dump(sq, f, indent=1)

    print(f"raw rows:               {n_raw}")
    print(f"dropped numeric codes:  {n_numeric}")
    print(f"qualifying rows:        {qual.height}")
    print(f"arrivals index rows:    {idx.height}")
    print(f"status quo:             {sq}")


if __name__ == "__main__":
    main()
