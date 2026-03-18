from __future__ import annotations

import time

import openai

from src.engines.base import EngineResponse, PROMPT_SUFFIX


class OpenAIAdapter:
    provider = "openai"

    def __init__(self, api_key: str | None = None, client=None, model: str = "gpt-5.4"):
        self.model = model
        self.client = client or openai.OpenAI(api_key=api_key)

    def query(self, prompt: str) -> EngineResponse:
        started = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=1024,
            messages=[{"role": "user", "content": prompt + PROMPT_SUFFIX}],
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return EngineResponse(
            provider=self.provider,
            prompt=prompt,
            raw_text=response.choices[0].message.content or "",
            latency_ms=latency_ms,
            metadata={"model": self.model},
        )
