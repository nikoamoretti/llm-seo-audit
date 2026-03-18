"""
Compatibility wrapper for querying multiple LLM providers.
"""

from __future__ import annotations

from src.engines.base import EngineResponse
from src.engines.runner import EngineRunner


class LLMQuerier:
    """Compatibility shim over the structured engine runner."""

    def __init__(self, api_keys: dict[str, str]):
        self.api_keys = api_keys
        self.runner = EngineRunner.from_api_keys(api_keys)

    def query_structured(self, provider: str, prompt: str) -> EngineResponse:
        """Return the normalized engine response."""
        return self.runner.query(provider, prompt)

    def query(self, provider: str, prompt: str) -> str:
        """Legacy string-only interface used by older callers."""
        return self.query_structured(provider, prompt).raw_text
