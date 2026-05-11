from __future__ import annotations

import json
from dataclasses import dataclass

from .models import Tool, raw_tools


@dataclass(frozen=True)
class PruneMetrics:
    original_tools: int
    selected_tools: int
    original_tokens: int
    selected_tokens: int
    reduced_tokens: int
    estimated_savings_usd: float


def estimate_metrics(
    tools: list[Tool],
    selected: list[Tool],
    price_per_million_tokens: float = 5.0,
) -> PruneMetrics:
    original_tokens = estimate_tokens(json.dumps(raw_tools(tools), separators=(",", ":")))
    selected_tokens = estimate_tokens(json.dumps(raw_tools(selected), separators=(",", ":")))
    reduced_tokens = max(0, original_tokens - selected_tokens)
    savings = (reduced_tokens / 1_000_000) * price_per_million_tokens
    return PruneMetrics(
        original_tools=len(tools),
        selected_tools=len(selected),
        original_tokens=original_tokens,
        selected_tokens=selected_tokens,
        reduced_tokens=reduced_tokens,
        estimated_savings_usd=savings,
    )


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))
