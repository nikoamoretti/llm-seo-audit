import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app as app_module


def _install_fake_openai(monkeypatch, content: str):
    class _FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=content)
                    )
                ]
            )

    class _FakeChat:
        def __init__(self):
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self, api_key: str):
            self.chat = _FakeChat()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeClient))


def test_lookup_llm_fallback_keeps_core_fields_but_strips_guessed_contact_fields(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.setattr(app_module, "detect_api_keys", lambda: {"openai": "test-openai-key"})

    places_calls = {"count": 0}

    def _fake_places_post(*args, **kwargs):
        places_calls["count"] += 1
        return SimpleNamespace(status_code=403, json=lambda: {})

    monkeypatch.setattr(app_module.requests, "post", _fake_places_post)
    _install_fake_openai(
        monkeypatch,
        """```json
        {"business_name":"Laveta Coffee","industry":"coffee shop","city":"Echo Park, Los Angeles, CA","website_url":"https://www.lavetacoffee.com","phone":"213-555-0100"}
        ```""",
    )

    client = TestClient(app_module.app)
    response = client.post("/api/lookup", json={"query": "Laveta Coffee Echo Park"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert places_calls["count"] == 0
    assert payload["results"] == [
        {
            "business_name": "Laveta Coffee",
            "industry": "coffee shop",
            "city": "Echo Park, Los Angeles, CA",
            "website_url": "",
            "phone": "",
            "address": "",
            "found": True,
        }
    ]


def test_lookup_does_not_treat_gemini_key_as_google_places_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.setattr(app_module, "detect_api_keys", lambda: {"gemini": "test-gemini-key"})

    places_calls = {"count": 0}

    def _fake_places_post(*args, **kwargs):
        places_calls["count"] += 1
        return SimpleNamespace(status_code=403, json=lambda: {})

    monkeypatch.setattr(app_module.requests, "post", _fake_places_post)

    client = TestClient(app_module.app)
    response = client.post("/api/lookup", json={"query": "Laveta Coffee Echo Park"})

    assert response.status_code == 200
    assert response.json() == {"results": [], "found": False}
    assert places_calls["count"] == 0
