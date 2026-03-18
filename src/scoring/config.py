from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


@lru_cache(maxsize=1)
def load_score_config() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[2] / "config" / "score_v2.yaml"
    with open(config_path) as file_obj:
        data = yaml.safe_load(file_obj)
    if not isinstance(data, dict):
        raise ValueError("score_v2.yaml must define a mapping.")
    return data
