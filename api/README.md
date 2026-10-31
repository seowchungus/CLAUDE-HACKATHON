# ACCORD console API + UI (W3)

## Run (mock, no data / no key)
```
. .venv/bin/activate
MOCK=1 uvicorn api.server:app --host 127.0.0.1 --port 8000   # localhost only, never --host 0.0.0.0; serves docs/fixtures, replays run_events.jsonl ~600 ms/event
cd web && npm install && npm run dev             # http://localhost:5173 (proxies /api to :8000)
```
Or build once (`cd web && npm run build`) and open http://localhost:8000/ (FastAPI serves `web/dist`).
`?autorun=1` starts a run on page load. `MOCK_GAP_S=0.05` speeds the replay up.

## Live
`uvicorn api.server:app --host 127.0.0.1 --port 8000` (no MOCK): scenarios from `core.scenario`/`core.bundle`/`core.mapdata`,
runs produced by `agents.coordinator.Coordinator(bundle, run_id).run()`, log/verify from `runs/<run_id>.jsonl` + `core.log.verify_chain`.

## Smoke test
```
R=$(curl -s -XPOST localhost:8000/api/runs -H 'content-type: application/json' -d '{"scenario_id":"2015-01-02_AA1234_DFW-ORD"}' | jq -r .run_id)
curl -N localhost:8000/api/runs/$R/stream
curl localhost:8000/api/runs/$R/verify
curl -XPOST localhost:8000/api/runs/$R/approve -H 'content-type: application/json' -d '{"action":"APPROVE","option_id":"opt_c1","by":"duty"}'
```
In mock mode, `POST /api/kill {"llm_enabled":false}` makes new runs replay a fallback-only stream (reason `LLM_KILLED`).
