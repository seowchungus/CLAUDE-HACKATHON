"""Merge shard files from run_eval --shard into one eval/results.json (summary recomputed from all rows).

  python -m eval.merge_results eval/results_partial_1of3.json eval/results_partial_2of3.json ... [--out PATH]
"""
import argparse
import json

from core.config import load_config, repo_path
from eval.run_eval import assemble


def merge(paths: list[str]) -> dict:
    parts = [json.load(open(repo_path(p))) for p in paths]
    seeds = {p["seed"] for p in parts}
    kinds = {p.get("llm") for p in parts}
    if len(seeds) != 1 or len(kinds) != 1:
        raise SystemExit(f"shards disagree: seeds={seeds} llm={kinds}")
    per, seen = [], set()
    for p in parts:
        for r in p["per_scenario"]:
            if r["scenario_id"] not in seen:
                per.append(r)
                seen.add(r["scenario_id"])
    res = assemble(per, seeds.pop(), kinds.pop())
    res["merged_from"] = [p.get("shard") for p in parts]
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", default=load_config()["paths"]["eval_results"])
    a = ap.parse_args()
    res = merge(a.paths)
    with open(repo_path(a.out), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(f"wrote {a.out}: n={res['n']} from {res['merged_from']}")


if __name__ == "__main__":
    main()
