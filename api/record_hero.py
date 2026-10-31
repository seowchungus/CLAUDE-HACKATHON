"""Record a live run's SSE envelopes for demo insurance.

    python -m api.record_hero <scenario_id> <name> [--mock]

Writes api/hero_cache/<name>.jsonl (one envelope per line); GET /api/replay/<name>/stream plays it back.
Without --mock this makes REAL LLM calls (subject to agents' budget guard): only run when MANAGER releases quota.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from api.server import CONFIG, HERO_DIR, new_run_id


async def record(scenario_id: str, name: str, mock: bool) -> Path:
    from agents.coordinator import Coordinator
    from core.bundle import build_bundle

    llm = None
    if mock:
        from agents.client import MockLLMClient

        llm = MockLLMClient(config=CONFIG)
    run_id = new_run_id()
    coord = Coordinator(build_bundle(scenario_id), run_id, config=CONFIG, llm=llm)
    HERO_DIR.mkdir(parents=True, exist_ok=True)
    out = HERO_DIR / f"{name}.jsonl"
    with open(out, "w") as f:
        async for env in coord.run():
            f.write(json.dumps(env, ensure_ascii=False) + "\n")
            print(env["seq"], env["type"])
    print(f"recorded {run_id} -> {out} (log: runs/{run_id}.jsonl)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario_id")
    ap.add_argument("name")
    ap.add_argument("--mock", action="store_true", help="use MockLLMClient (no API calls)")
    a = ap.parse_args()
    asyncio.run(record(a.scenario_id, a.name, a.mock))


if __name__ == "__main__":
    main()
