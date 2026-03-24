from __future__ import annotations

import time

try:
    from google import genai
except ImportError:  # pragma: no cover - exercised via adapter construction.
    genai = None

from src.engines.base import EngineResponse, PROMPT_SUFFIX


class GeminiAdapter:
    provider = "gemini"

    def __init__(self, api_key: str | None = None, client=None, model: str = "gemini-3.1-flash-lite-preview"):
        self.model = model
        if client is not None:
            self.client = client
            return
        if genai is None:
            raise ImportError("google.genai is required to use the Gemini adapter without an injected client.")
        self.client = genai.Client(api_key=api_key)

    def query(self, prompt: str) -> EngineResponse:
        started = time.perf_counter()
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt + PROMPT_SUFFIX,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return EngineResponse(
            provider=self.provider,
            prompt=prompt,
            raw_text=response.text or "",
            latency_ms=latency_ms,
            metadata={"model": self.model},
        )
