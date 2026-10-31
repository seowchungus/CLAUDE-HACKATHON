import pytest

from agents.budget import LEDGER_ENV


@pytest.fixture(autouse=True)
def _tmp_llm_ledger(tmp_path, monkeypatch):
    """No agents test may touch the real runs/llm_budget.json: every test gets its own ledger."""
    monkeypatch.setenv(LEDGER_ENV, str(tmp_path / "llm_budget_test.json"))
