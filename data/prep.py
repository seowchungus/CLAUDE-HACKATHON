"""One-off data prep (proposal §2.1). Run from repo root: python data/prep.py

Writes:
  data/qualifying.parquet     rows with WEATHER_DELAY > 15 OR LATE_AIRCRAFT_DELAY > 20, not cancelled/diverted
  data/arrivals_index.parquet all non-cancelled flights, narrow columns (banks, connections, next-tail departures)
  data/status_quo.json        computed status-quo cost over the qualifying rows
  data/airport_limits.json    the organisers' workbook (challenge2_operational_constraints.xlsx), extracted with
                              stdlib zipfile + xml.etree: {airports: {IATA: limits}, defaults_by_size_class, sheets}
Rows whose ORIGIN/DEST are not 3-letter alphabetic IATA codes (October numeric-ID quirk) are dropped and counted.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
import zipfile

import polars as pl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import load_config, repo_path  # noqa: E402

IATA_RE = r"^[A-Z]{3}$"
STR_COLS = {"AIRLINE": pl.Utf8, "TAIL_NUMBER": pl.Utf8, "ORIGIN_AIRPORT": pl.Utf8,
            "DESTINATION_AIRPORT": pl.Utf8, "CANCELLATION_REASON": pl.Utf8}
INDEX_COLS = ["DATE", "AIRLINE", "FLIGHT_NUMBER", "TAIL_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT",
              "SCHEDULED_DEPARTURE", "SCHEDULED_ARRIVAL", "ARRIVAL_DELAY", "DEPARTURE_DELAY", "DISTANCE"]


_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
LIMIT_KEYS = {"size_class": str, "active_runways": int, "gates": int, "max_runway_ops_per_hour": int,
              "min_turnaround_min": int, "spare_gates_at_any_time": int}


def read_xlsx(path: str) -> dict[str, list[list[str]]]:
    """Every sheet as a list of rows of cell strings (no openpyxl dependency)."""
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out: dict[str, list[list[str]]] = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", _NS):
        target = rels[sh.get(f"{{{_NS['r']}}}id")].lstrip("/")
        target = target if target.startswith("xl/") else f"xl/{target}"
        rows = []
        for row in ET.fromstring(z.read(target)).find("m:sheetData", _NS):
            vals = []
            for c in row:
                v, t = c.find("m:v", _NS), c.get("t")
                if t == "s":
                    vals.append(shared[int(v.text)])
                elif t == "inlineStr":
                    vals.append("".join(x.text or "" for x in c.iter(f"{{{_NS['m']}}}t")))
                else:
                    vals.append(v.text if v is not None else "")
            rows.append(vals)
        out[sh.get("name")] = rows
    return out


def extract_workbook(cfg: dict) -> dict:
    sheets = read_xlsx(repo_path(cfg["workbook"]["path"]))
    cap = sheets["airport_capacity"]
    hdr_i = next(i for i, r in enumerate(cap) if r and r[0] == "IATA_CODE")
    hdr = cap[hdr_i]
    airports_: dict[str, dict] = {}
    defaults: dict[str, dict] = {}
    for r in cap[hdr_i + 1:]:
        if not r or not r[0]:
            continue
        rec = dict(zip(hdr, r))
        lim = {k: f(float(rec[k])) if f is int else rec[k] for k, f in LIMIT_KEYS.items()}
        airports_[rec["IATA_CODE"]] = lim
        defaults.setdefault(lim["size_class"], lim)
    res = {"source": cfg["workbook"]["path"], "note": cap[0][0] if cap and cap[0] else "",
           "airports": airports_, "defaults_by_size_class": defaults,
           "sheets": {k: v for k, v in sheets.items() if k != "airport_capacity"}}
    with open(repo_path(cfg["workbook"]["extracted"]), "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    return res


def main() -> None:
    cfg = load_config()
    wb = extract_workbook(cfg)
    print(f"workbook airports:      {len(wb['airports'])} (size classes {sorted(wb['defaults_by_size_class'])})")
    if "--workbook-only" in sys.argv:
        return
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
