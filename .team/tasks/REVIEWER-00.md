# REVIEWER-00: Audit the frozen contracts
Owner: REVIEWER · Timebox: 15 min · Proposal: §1.3, §4, §5, §6, §8

## Goal
Catch contract gaps now, before three workers build on them.

## Do
Read `docs/CONTRACTS.md`, `config.yaml` and the fixtures in `docs/fixtures/` against `ACCORD_proposal.md`. Check:
1. Every challenge requirement in proposal §1.3 has a home in the contracts (types, events or endpoints).
2. Every metric named in proposal §5.1 and §8.3 can be computed from what the contracts carry (e.g. "unsafe proposals blocked" needs `veto` and `counter_checked`; latency and tokens need `AgentMessage` fields).
3. The SSE events are enough for the UI items in proposal §7 (map, wall, Gantt, chaos, kill, approve, log badge).
4. The fixtures conform to the contracts (spot-check field names; `docs/fixtures/run_log.jsonl` should verify with the §5 hash formula; you can check with a 10-line stdlib script).
5. Anything ambiguous enough that two workers would implement it differently.

## Output
`.team/reviews/REVIEWER-00.md` with VERDICT `APPROVED` or `CHANGES` and a numbered list. Only list things that would cause an integration break or a non-negotiable miss; skip style. Then tell the human one line.

## After this
Wait for review requests. While idle, prepare: write `.team/reviews/_integration_checklist.md`, a 10-step smoke test for the 13:39 integration (start server live, run a dev scenario, chaos, kill, approve, download log, verify).
