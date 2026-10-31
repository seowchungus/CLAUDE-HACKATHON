"""Mock-mode API contract checks (W3-01-fix items 4-5, v1.1 approve rules). Never calls Gemini."""
import os
import time

os.environ["MOCK"] = "1"
os.environ["MOCK_GAP_S"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from api import server  # noqa: E402

SID = "2015-01-02_AA1234_DFW-ORD"


def _drain(c: TestClient, run_id: str, until: str = "run_ended", timeout: float = 10) -> list:
    t = time.time()
    while time.time() - t < timeout:
        run = server.manager.get(run_id)
        if any(e["type"] == until for e in run.events):
            return run.events
        time.sleep(0.05)
    raise AssertionError(f"no {until}")


def _start(c: TestClient, **body) -> str:
    rid = c.post("/api/runs", json={"scenario_id": SID, **body}).json()["run_id"]
    with c.stream("GET", f"/api/runs/{rid}/stream") as r:  # subscribing starts the producer
        for line in r.iter_lines():
            if line.startswith("event: run_ended"):
                break
    return rid


def test_unknown_scenario_404():
    with TestClient(server.app) as c:
        assert c.get("/api/scenarios/nope").status_code == 404
        assert c.post("/api/runs", json={"scenario_id": "nope"}).status_code == 404


def test_chaos_body_validated():
    with TestClient(server.app) as c:
        rid = c.post("/api/runs", json={"scenario_id": SID}).json()["run_id"]
        assert c.post(f"/api/runs/{rid}/chaos", json={"kind": "METEOR"}).status_code == 422


def test_replay_chain_and_approve_rules():
    with TestClient(server.app) as c:
        rid = c.post("/api/runs", json={"scenario_id": SID}).json()["run_id"]
        assert c.post(f"/api/runs/{rid}/approve", json={"action": "APPROVE", "option_id": "opt_c1", "by": "t"}).status_code == 409
        rid = _start(c)
        v = c.get(f"/api/runs/{rid}/verify").json()
        assert v["ok"] and v["n_entries"] == 29
        r = c.post(f"/api/runs/{rid}/approve", json={"action": "APPROVE", "option_id": "opt_c1", "by": "t"})
        assert r.status_code == 200 and r.json()["final_hash"] == v["head_hash"]
        v2 = c.get(f"/api/runs/{rid}/verify").json()
        assert v2["ok"] and v2["n_entries"] == 30
        ev = server.manager.get(rid).events[-1]
        assert ev["type"] == "approved" and ev["log_hash"] == v2["head_hash"] and ev["data"]["final_hash"] == v["head_hash"]
        assert c.post(f"/api/runs/{rid}/approve", json={"action": "APPROVE", "option_id": "opt_c1", "by": "t"}).status_code == 409


def test_killed_stream_has_distinct_hashes_and_verifies():
    with TestClient(server.app) as c:
        c.post("/api/kill", json={"llm_enabled": False})
        try:
            rid = _start(c)
        finally:
            c.post("/api/kill", json={"llm_enabled": True})
        evs = server.manager.get(rid).events
        assert [e["type"] for e in evs][-3:] == ["fallback", "awaiting_approval", "run_ended"]
        hashes = [e["log_hash"] for e in evs]
        assert len(set(hashes)) == len(hashes)
        log = c.get(f"/api/runs/{rid}/log").text.strip().splitlines()
        assert c.get(f"/api/runs/{rid}/verify").json()["ok"] and len(log) == len(evs) + 1
