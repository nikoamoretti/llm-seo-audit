from types import SimpleNamespace

import pytest

from src.engines.anthropic_adapter import AnthropicAdapter
from src.engines import gemini_adapter as gemini_module
from src.engines.gemini_adapter import GeminiAdapter
from src.engines.openai_adapter import OpenAIAdapter
from src.engines.perplexity_adapter import PerplexityAdapter


class _FakeAnthropicClient:
    class messages:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(content=[SimpleNamespace(text="Anthropic result")], id="anthropic-1")


class _FakeOpenAIClient:
    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="OpenAI result"))],
                    model="gpt-test",
                )


class _FakeGeminiClient:
    class models:
        @staticmethod
        def generate_content(**kwargs):
            return SimpleNamespace(text="Gemini result")


def test_openai_adapter_returns_normalized_response():
    adapter = OpenAIAdapter(client=_FakeOpenAIClient(), model="gpt-test")

    result = adapter.query("Who are the best dentists in Phoenix?")

    assert result.provider == "openai"
    assert result.prompt == "Who are the best dentists in Phoenix?"
    assert result.raw_text == "OpenAI result"
    assert result.latency_ms >= 0
    assert result.metadata["model"] == "gpt-test"


def test_anthropic_adapter_returns_normalized_response():
    adapter = AnthropicAdapter(client=_FakeAnthropicClient(), model="claude-test")

    result = adapter.query("Who are the best plumbers in Austin?")

    assert result.provider == "anthropic"
    assert result.raw_text == "Anthropic result"
    assert result.metadata["model"] == "claude-test"


def test_gemini_adapter_returns_normalized_response():
    adapter = GeminiAdapter(client=_FakeGeminiClient(), model="gemini-test")

    result = adapter.query("Who are the best lawyers in Los Angeles?")

    assert result.provider == "gemini"
    assert result.raw_text == "Gemini result"
    assert result.metadata["model"] == "gemini-test"


def test_gemini_adapter_requires_sdk_when_no_client_is_injected(monkeypatch):
    monkeypatch.setattr(gemini_module, "genai", None)

    with pytest.raises(ImportError, match="google.genai"):
        GeminiAdapter(api_key="test-key")


def test_perplexity_adapter_returns_normalized_response():
    adapter = PerplexityAdapter(client=_FakeOpenAIClient(), model="sonar-test")

    result = adapter.query("Who are the best coffee shops in Echo Park?")

    assert result.provider == "perplexity"
    assert result.raw_text == "OpenAI result"
    assert result.metadata["model"] == "sonar-test"
