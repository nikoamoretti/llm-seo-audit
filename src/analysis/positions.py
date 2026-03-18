from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PositionResult:
    position: int | None
    total_items: int
    position_normalized: float


def detect_position(response: str, name_variants: list[str]) -> PositionResult:
    normalized_variants = [variant.lower() for variant in name_variants]
    lines = response.split("\n")
    position = None
    current_pos = 0
    max_pos = 0

    for line in lines:
        numbered = re.match(r"\s*(?:#?\s*)?(\d+)[.):\s]", line)
        if numbered:
            current_pos = int(numbered.group(1))
        elif re.match(r"\s*[-*]\s", line):
            current_pos += 1
        elif re.match(r"\s*\*\*", line):
            current_pos += 1

        max_pos = max(max_pos, current_pos)
        line_lower = line.lower()
        if position is None and any(variant in line_lower for variant in normalized_variants):
            position = current_pos if current_pos > 0 else 1

    if position is None and any(variant in response.lower() for variant in normalized_variants):
        position = 1
    total_items = max(max_pos, 1 if position else 0)

    if position is not None and total_items > 1:
        normalized = max(0.0, 1.0 - (position - 1) / (total_items - 1))
    elif position == 1:
        normalized = 1.0
    else:
        normalized = 0.0

    return PositionResult(position=position, total_items=total_items, position_normalized=round(normalized, 3))
