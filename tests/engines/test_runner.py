import pytest

from src.engines.base import EngineAdapter, EngineResponse
from src.engines.runner import EngineRunner


class _StaticAdapter(EngineAdapter):
    def __init__(self, provider: str, text: str):
        self.provider = provider
        self._text = text

    def query(self, prompt: str) -> EngineResponse:
        return EngineResponse(
            provider=self.provider,
            prompt=prompt,
            raw_text=self._text,
            latency_ms=12,
            metadata={"provider": self.provider},
        )


def test_runner_returns_normalized_response_for_provider():
    runner = EngineRunner(
        adapters={
            "openai": _StaticAdapter("openai", "OpenAI text"),
            "anthropic": _StaticAdapter("anthropic", "Anthropic text"),
        }
    )

    result = runner.query("openai", "Test prompt")

    assert result.provider == "openai"
    assert result.prompt == "Test prompt"
    assert result.raw_text == "OpenAI text"


def test_runner_exposes_available_providers_and_rejects_unknown_provider():
    runner = EngineRunner(adapters={"openai": _StaticAdapter("openai", "OpenAI text")})

    assert runner.available_providers() == ["openai"]

    with pytest.raises(ValueError):
        runner.query("gemini", "Test prompt")
