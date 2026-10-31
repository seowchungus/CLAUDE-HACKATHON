"""Run one full negotiation and print the SSE event stream, one JSON per line.

python -m agents.run_fixture [--mock|--mock-deadlock|--mock-unsafe|--mock-hallucinate|--killed] [--bundle PATH]
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
import secrets

from core.config import load_config
from core.log import verify_chain
from agents import killswitch
from agents.bundles import FIXTURE_BUNDLE, load_bundle
from agents.coordinator import Coordinator


def new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{secrets.token_hex(3)}"


async def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--mock", action="store_true")
    g.add_argument("--mock-deadlock", action="store_true")
    g.add_argument("--mock-unsafe", action="store_true")
    g.add_argument("--mock-hallucinate", action="store_true")
    g.add_argument("--killed", action="store_true")
    ap.add_argument("--bundle", default=FIXTURE_BUNDLE)
    args = ap.parse_args(argv)

    cfg = load_config()
    llm = None
    if args.mock or args.mock_deadlock or args.mock_unsafe or args.mock_hallucinate or args.killed:
        from agents.client import MockLLMClient
        mode = ("deadlock" if args.mock_deadlock else "unsafe" if args.mock_unsafe
                else "hallucinate" if args.mock_hallucinate else "normal")
        llm = MockLLMClient(mode=mode, config=cfg)
    if args.killed:
        killswitch.set_llm_enabled(False)
    coord = Coordinator(load_bundle(args.bundle), new_run_id(), config=cfg, llm=llm)
    async for env in coord.run():
        print(json.dumps(env, ensure_ascii=False), flush=True)
    v = verify_chain(coord.log.path)
    print(f"# log: {coord.log.path}  verify: ok={v.ok} n={v.n_entries}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
