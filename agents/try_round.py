"""Smoke test for one round: render three prompts, make THREE separate parallel calls, print results.

python -m agents.try_round [--mock] [--bundle docs/fixtures/scenario_bundle.json] [--show-prompt ATC]
"""
import argparse
import asyncio
import json

from core.config import load_config
from agents.bundles import FIXTURE_BUNDLE, load_bundle
from agents.prompting import ROLES, RoundState, build_call


async def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--bundle", default=FIXTURE_BUNDLE)
    ap.add_argument("--show-prompt", choices=ROLES)
    ap.add_argument("--round", type=int, default=1)
    args = ap.parse_args(argv)

    cfg = load_config()
    b = load_bundle(args.bundle)
    st = RoundState(round=args.round, candidates=[o.option_id for o in b.options],
                    tentative=b.fallback.option_id if args.round > 1 else None)
    calls = {r: build_call(b.scenario, b.options, b.checks, r, st, cfg) for r in ROLES}
    if args.show_prompt:
        print(calls[args.show_prompt].prompt)
        return
    if args.mock:
        from agents.client import MockLLMClient
        llm = MockLLMClient(config=cfg)
    else:
        from agents.client import GeminiClient
        llm = GeminiClient(cfg)
    msgs = await asyncio.gather(*(llm.position(r, c.prompt, c.response_model, c.round, call=c)
                                  for r, c in calls.items()))
    for m in msgs:
        print(json.dumps(m.model_dump(mode="json"), indent=2))
    print(f"# {len(msgs)} separate calls; statuses: {[m.status for m in msgs]}")


if __name__ == "__main__":
    asyncio.run(main())
