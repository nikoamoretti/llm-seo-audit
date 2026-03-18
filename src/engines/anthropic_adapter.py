from __future__ import annotations

import time

import anthropic

from src.engines.base import EngineResponse, PROMPT_SUFFIX


class AnthropicAdapter:
    provider = "anthropic"

    def __init__(self, api_key: str | None = None, client=None, model: str = "claude-sonnet-4-6"):
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key)

    def query(self, prompt: str) -> EngineResponse:
        started = time.perf_counter()
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt + PROMPT_SUFFIX}],
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw_text = ""
        for block in getattr(message, "content", []):
            text = getattr(block, "text", None)
            if isinstance(text, str) and text:
                raw_text = text
                break
        return EngineResponse(
            provider=self.provider,
            prompt=prompt,
            raw_text=raw_text,
            latency_ms=latency_ms,
            metadata={"model": self.model},
        )
