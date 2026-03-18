from llm_querier import LLMQuerier
from src.engines.base import EngineResponse


class _FakeRunner:
    def query(self, provider: str, prompt: str) -> EngineResponse:
        return EngineResponse(
            provider=provider,
            prompt=prompt,
            raw_text="Structured result",
            latency_ms=25,
            metadata={"provider": provider},
        )


def test_llm_querier_exposes_structured_query_result():
    querier = LLMQuerier(api_keys={})
    querier.runner = _FakeRunner()

    result = querier.query_structured("openai", "Test prompt")

    assert result.provider == "openai"
    assert result.prompt == "Test prompt"
    assert result.raw_text == "Structured result"
