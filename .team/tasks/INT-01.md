# INT-01: Live integration (coordinator → SSE → console on real data)
**STATUS: AWAITING HUMAN APPROVAL. Do not start.** (Integration is a major phase; the human approves its start.)

Owners: W3 (lead, `api/`, `web/`), W2 (support, `agents/`), W1 (support, `core/`), REVIEWER runs `.team/reviews/_integration_checklist.md` → `.team/reviews/INT-smoke.md`.
Timebox: 45 min · Depends on: W1-05, W2-03, W3-03.

## Goal
`uvicorn api.server:app` without `MOCK` serves real qualifying rows; a run streams real Gemini negotiation into the console; chaos, kill, approve, log download and verify all work live.

## Steps
1. W3: live producer = `core.bundle.build_bundle(scenario_id, chaos)` + `Coordinator(bundle, run_id, config).run()`; `/bundle` returns the run's bundle and `core.mapdata.map_payload`; `/verify` uses `core.log.verify_chain`; `/record` uses `agents.narrator.record_markdown`; chaos cancels the parent via `Coordinator.cancel()`.
2. W2: on-call for coordinator issues seen in the live UI; fix within `agents/`.
3. W1: on-call for scenario/metric issues; fix within `core/`.
4. REVIEWER: runs the 10-step smoke checklist on a dev row and both hero golden scenarios; files FAIL items as numbered CHANGES.

## Acceptance
All 10 smoke steps PASS (or a FAIL with an accepted, logged workaround in BOARD.md).
