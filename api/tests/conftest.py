"""API tests never touch the real LLM ledger (runs/llm_budget.json) and never call Gemini."""
import os
import tempfile

_LEDGER_DIR = tempfile.mkdtemp(prefix="accord-api-tests-")
os.environ["ACCORD_LLM_LEDGER"] = os.path.join(_LEDGER_DIR, "llm_budget.json")
os.environ["MOCK"] = "1"
os.environ.setdefault("MOCK_GAP_S", "0")
