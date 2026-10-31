"""Fake google-genai client for testing GeminiClient with no network."""
import json
from types import SimpleNamespace


class FakeAPIError(Exception):
    def __init__(self, code, msg=""):
        super().__init__(f"{code} {msg}")
        self.code = code


class FakeModels:
    def __init__(self, script):
        self.script = list(script)     # each item: dict (JSON answer), str (raw text) or Exception
        self.requests = []

    async def generate_content(self, model, contents, config):
        self.requests.append({"model": model, "contents": contents, "config": config})
        item = self.script.pop(0) if self.script else FakeAPIError(500, "script exhausted")
        if isinstance(item, Exception):
            raise item
        text = item if isinstance(item, str) else json.dumps(item)
        return SimpleNamespace(text=text, usage_metadata=SimpleNamespace(
            prompt_token_count=100, candidates_token_count=20, thoughts_token_count=0))


def install(gemini_client, script):
    models = FakeModels(script)
    fake = SimpleNamespace(aio=SimpleNamespace(models=models))
    for name in gemini_client._clients:
        gemini_client._clients[name] = fake
    return models
