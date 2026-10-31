import os

from eval.run_eval import run


def test_eval_mock_end_to_end(monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    res = run(2, "mock")
    assert res["measured"] is True and res["n"] == 2
    s = res["summary"]
    assert s["unsafe_plans_executed"] == 0
    assert s["consensus_rate"] is not None and s["J_mean"]["B1_optimizer"] is not None
    for p in res["per_scenario"]:
        assert p["final_state"] in ("CONSENSUS", "FALLBACK", "ESCALATE")
        assert os.path.exists(f"runs/{p['run_id']}.jsonl")


def test_eval_shards_partition():
    a = run(4, "none", shard=(1, 2))["per_scenario"]
    b = run(4, "none", shard=(2, 2))["per_scenario"]
    ids = {p["scenario_id"] for p in a} | {p["scenario_id"] for p in b}
    assert len(ids) == 4 and not ({p["scenario_id"] for p in a} & {p["scenario_id"] for p in b})


def test_ungrounded_rate_null_without_llm_and_counted_with_mock(monkeypatch):
    assert run(2, "none")["summary"]["ungrounded_rate"] is None
    monkeypatch.setenv("MOCK", "1")
    res = run(2, "mock")
    s, per = res["summary"], res["per_scenario"]
    ok = sum(p["n_ok_positions"] for p in per)
    assert ok > 0 and s["ungrounded_rate"] == round(sum(p["n_ungrounded"] for p in per) / ok, 3)
