import json

from core.log import ConsensusLog, verify_chain
from core.types import Scenario, ScenarioBundle

FIXTURE = "docs/fixtures/scenario_bundle.json"


def _scenario() -> Scenario:
    return ScenarioBundle.model_validate(json.load(open(FIXTURE))["bundle"]).scenario


def test_append_and_verify(tmp_path):
    log = ConsensusLog("run_test_ok", _scenario(), runs_dir=str(tmp_path))
    for i in range(5):
        log.append("agent_thinking", "COORDINATOR", {"round": 1, "i": i})
    assert len(log.entries()) == 6
    assert log.entries()[0].event_type == "scenario_loaded"
    assert "aar_reduced" in log.entries()[0].synthetic_fields
    res = verify_chain(log.path)
    assert res.ok and res.n_entries == 6 and res.broken_at is None
    assert res.head_hash == log.head_hash()


def test_tamper_detected(tmp_path):
    log = ConsensusLog("run_test_tamper", _scenario(), runs_dir=str(tmp_path))
    for i in range(5):
        log.append("veto", "CHECKER", {"round": 1, "i": i}, ["H3_fuel_reserve"])
    lines = open(log.path).read().splitlines()
    lines[3] = lines[3].replace('"i":2', '"i":7').replace('"i": 2', '"i": 7')
    assert lines[3] != open(log.path).read().splitlines()[3]
    open(log.path, "w").write("\n".join(lines) + "\n")
    res = verify_chain(log.path)
    assert not res.ok and res.broken_at == 3


def test_fixture_log_verifies():
    assert verify_chain("docs/fixtures/run_log.jsonl").ok



def test_resume_continues_chain(tmp_path):
    log = ConsensusLog("run_test_resume", _scenario(), runs_dir=str(tmp_path))
    log.append("run_started", "COORDINATOR", {"x": 1})
    head = log.head_hash()
    log2 = ConsensusLog("run_test_resume", _scenario(), runs_dir=str(tmp_path))
    assert len(log2.entries()) == 2 and log2.head_hash() == head
    e = log2.append("approved", "HUMAN", {"final_hash": head})
    assert e.seq == 2 and e.prev_hash == head
    res = verify_chain(log2.path)
    assert res.ok and res.n_entries == 3


def test_append_deep_copies(tmp_path):
    log = ConsensusLog("run_test_copy", _scenario(), runs_dir=str(tmp_path))
    payload = {"options": [1, 2]}
    log.append("options", "CHECKER", payload)
    payload["options"].append(3)
    assert log.entries()[-1].payload == {"options": [1, 2]}
    assert verify_chain(log.path).ok


REQUIRED_PROVENANCE = ["row", "disruption_type", "disruption_min", "origin", "destination", "disrupted", "bank",
                       "connections", "base_eta_min", "aar_nominal", "aar_reduced", "aircraft_size",
                       "fuel_at_fix_min", "flight_crew_duty_remaining_min", "ramp_shift_end_min",
                       "next_departure_min", "gates", "taxiways", "blocked_taxiways", "turbulence_by_fp",
                       "chaos_applied", "disrupted.wake", "bank.wake", "connections.wake",
                       "connections.pax_connecting"]


def test_provenance_required_keys_all_dev_rows():
    from core.scenario import build_scenario, dev_scenario_ids
    for sid in dev_scenario_ids():
        s = build_scenario(sid)
        missing = [k for k in REQUIRED_PROVENANCE if k not in s.provenance]
        assert not missing, (sid, missing)
        assert s.disrupted.flight_id == f"{s.row.airline}{s.row.flight_number}"  # unpadded
        assert all(f.flight_id == f"{f.airline}{f.flight_number}" for f in s.bank + s.connections)
