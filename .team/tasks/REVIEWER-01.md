# REVIEWER-01: Review the first build wave
Owner: REVIEWER · Timebox: 40 min · Depends on: commits W1-01..04, W2-01..02, W3-01..02

Thanks for REVIEWER-00. All 8 items are resolved in CONTRACTS v1.1 (see its changelog) and the fixtures were regenerated (`run_log.jsonl` verifies now). Note: `agents/tests/test_shape_matches_fixture` fails until W2-03 adds `counter_checked.failed`; that's expected, not a review finding.

Review against **v1.0 plus anything that contradicts v1.1 and isn't already in W1-05/W2-03/W3-03** (read those task files so you don't duplicate them). One review file per worker, in this priority order (non-negotiables live mostly in W2 and W1-03):

1. `.team/reviews/W2-01_02.md`: three separate calls per round; MAX_ROUNDS enforced in code; R3 has no counters; the checker overrides (incl. unanimous accept); kill → fallback with 0 calls; LLM never computes or checks legality (read the prompt template and the coordinator); 429 back-off; key handling.
2. `.team/reviews/W1-01_04.md`: H1–H7 rules vs proposal §5.2; fallback never infeasible; ESCALATE; seeded reproducibility; every synthetic field labelled; status-quo numbers computed; the hash formula.
3. `.team/reviews/W3-01_02.md`: endpoint shapes vs §4; SSE format; synthetic tags in the UI; the verify endpoint uses the contract formula.

For each: VERDICT + numbered CHANGES. I'll fold the CHANGES into the workers' next tasks.
