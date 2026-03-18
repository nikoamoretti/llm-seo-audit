from __future__ import annotations

from src.engines.anthropic_adapter import AnthropicAdapter
from src.engines.base import EngineAdapter, EngineResponse
from src.engines.gemini_adapter import GeminiAdapter
from src.engines.openai_adapter import OpenAIAdapter
from src.engines.perplexity_adapter import PerplexityAdapter


class EngineRunner:
    def __init__(self, adapters: dict[str, EngineAdapter]):
        self.adapters = adapters

    @classmethod
    def from_api_keys(cls, api_keys: dict[str, str]) -> "EngineRunner":
        adapters: dict[str, EngineAdapter] = {}
        if "anthropic" in api_keys:
            adapters["anthropic"] = AnthropicAdapter(api_key=api_keys["anthropic"])
        if "openai" in api_keys:
            adapters["openai"] = OpenAIAdapter(api_key=api_keys["openai"])
        if "gemini" in api_keys:
            adapters["gemini"] = GeminiAdapter(api_key=api_keys["gemini"])
        if "perplexity" in api_keys:
            adapters["perplexity"] = PerplexityAdapter(api_key=api_keys["perplexity"])
        return cls(adapters=adapters)

    def available_providers(self) -> list[str]:
        return sorted(self.adapters)

    def query(self, provider: str, prompt: str) -> EngineResponse:
        adapter = self.adapters.get(provider)
        if adapter is None:
            raise ValueError(f"Unknown provider: {provider}")
        return adapter.query(prompt)
