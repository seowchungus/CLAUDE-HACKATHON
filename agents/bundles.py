"""Load a ScenarioBundle from JSON (the fixture, or a cached bundle) for CLIs, tests and no-data mock mode."""
import json

from core.config import repo_path
from core.types import ScenarioBundle

FIXTURE_BUNDLE = "docs/fixtures/scenario_bundle.json"


def load_bundle(path: str = FIXTURE_BUNDLE) -> ScenarioBundle:
    with open(repo_path(path), encoding="utf-8") as f:
        data = json.load(f)
    return ScenarioBundle.model_validate(data.get("bundle", data))
