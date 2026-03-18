import app as app_module
from src.engines.base import EngineResponse


class _FakeQuerier:
    def query_structured(self, provider: str, prompt: str) -> EngineResponse:
        return EngineResponse(
            provider=provider,
            prompt=prompt,
            raw_text="Laveta Coffee is cited by https://lavetacoffee.com",
            latency_ms=11,
            metadata={"provider": provider},
        )


class _FakeAnalyzer:
    def analyze_response(self, response: str, query: str) -> dict:
        return {
            "mentioned": True,
            "recommended": True,
            "cited": True,
            "cited_official_domain": True,
            "cited_third_party_domain": False,
            "citations": [{"label": "Laveta Coffee", "url": "https://lavetacoffee.com"}],
            "position": 1,
            "total_items": 1,
            "position_normalized": 1.0,
            "sentiment": 0.4,
            "accuracy": 1.0,
            "visibility_score": 90.0,
            "competitors": [],
            "attributes": [],
        }

    def empty_analysis(self) -> dict:
        return {}


def test_query_single_preserves_structured_engine_response():
    result = app_module._query_single(
        _FakeQuerier(),
        "openai",
        {"text": "Who are the best coffee shops in Echo Park?", "cluster": "discovery"},
        _FakeAnalyzer(),
    )

    assert result["query"] == "Who are the best coffee shops in Echo Park?"
    assert result["engine_response"]["provider"] == "openai"
    assert result["engine_response"]["latency_ms"] == 11
    assert result["analysis"]["citations"][0]["url"] == "https://lavetacoffee.com"
