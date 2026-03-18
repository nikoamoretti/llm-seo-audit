from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


PROMPT_SUFFIX = (
    "\n\nPlease provide specific business names and brief reasons for each recommendation. "
    "List them in order of your confidence in the recommendation."
)


@dataclass(frozen=True)
class EngineResponse:
    provider: str
    prompt: str
    raw_text: str
    latency_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)


class EngineAdapter(Protocol):
    provider: str

    def query(self, prompt: str) -> EngineResponse:
        ...
