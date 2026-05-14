from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter

from .cache import get_cached_selection, store_selection
from .metrics import PruneMetrics, estimate_metrics
from .models import Tool
from .providers import ProviderError, select_with_provider
from .ranker import PromptAliases, select_tools


@dataclass(frozen=True)
class SelectionResult:
    selected: list[Tool]
    requested_provider: str
    provider: str
    fallback_used: bool
    cache_hit: bool
    duration_ms: int
    metrics: PruneMetrics
    warning: str | None = None


def select_resilient(
    provider: str,
    prompt: str,
    tools: list[Tool],
    limit: int = 5,
    model: str | None = None,
    fallback: str = "heuristic",
    timeout_ms: int = 800,
    cache_enabled: bool = False,
    logger: logging.Logger | None = None,
    price_per_million_tokens: float = 5.0,
    keep: tuple[str, ...] | list[str] = (),
    prompt_aliases: PromptAliases | None = None,
) -> SelectionResult:
    if limit <= 0:
        raise ValueError("limit must be greater than zero.")

    logger = logger or logging.getLogger("context_janitor")
    started = perf_counter()
    requested_provider = provider

    keep_names = tuple(name for name in keep if name)

    if cache_enabled and not keep_names:
        cache_entry = get_cached_selection(prompt, tools, provider, model, limit, prompt_aliases=prompt_aliases)
        cached = _tools_by_names(cache_entry.names if cache_entry else [], tools, limit)
        if cached:
            metrics = estimate_metrics(tools, cached, price_per_million_tokens)
            logger.info(
                "Cache hit for provider=%s similarity=%.2f selected=%s",
                provider,
                cache_entry.similarity if cache_entry else 0,
                [tool.name for tool in cached],
            )
            return SelectionResult(
                selected=cached,
                requested_provider=requested_provider,
                provider=f"{provider}:cache",
                fallback_used=False,
                cache_hit=True,
                duration_ms=_elapsed_ms(started),
                metrics=metrics,
            )

    try:
        selected = select_with_provider(provider, prompt, tools, limit, model, timeout_ms / 1000, prompt_aliases)
        actual_provider = provider
        fallback_used = False
        warning = None
    except ProviderError as error:
        if fallback != "heuristic":
            raise
        warning = f"{provider} unavailable; fell back to heuristic: {error}"
        logger.warning(warning)
        selected = select_tools(prompt, tools, limit, prompt_aliases)
        actual_provider = "heuristic"
        fallback_used = True

    selected = _apply_keep(selected, tools, keep_names, limit)

    if cache_enabled and not keep_names:
        try:
            store_selection(prompt, tools, selected, provider, model, limit, prompt_aliases=prompt_aliases)
        except OSError as error:
            logger.warning("Could not write cache: %s", error)

    metrics = estimate_metrics(tools, selected, price_per_million_tokens)
    return SelectionResult(
        selected=selected,
        requested_provider=requested_provider,
        provider=actual_provider,
        fallback_used=fallback_used,
        cache_hit=False,
        duration_ms=_elapsed_ms(started),
        metrics=metrics,
        warning=warning,
    )


async def select_resilient_async(
    provider: str,
    prompt: str,
    tools: list[Tool],
    limit: int = 5,
    model: str | None = None,
    fallback: str = "heuristic",
    timeout_ms: int = 800,
    cache_enabled: bool = False,
    logger: logging.Logger | None = None,
    price_per_million_tokens: float = 5.0,
    keep: tuple[str, ...] | list[str] = (),
    prompt_aliases: PromptAliases | None = None,
) -> SelectionResult:
    return await asyncio.to_thread(
        select_resilient,
        provider,
        prompt,
        tools,
        limit,
        model,
        fallback,
        timeout_ms,
        cache_enabled,
        logger,
        price_per_million_tokens,
        keep,
        prompt_aliases,
    )


def _tools_by_names(names: list[str], tools: list[Tool], limit: int) -> list[Tool]:
    by_name = {tool.name: tool for tool in tools}
    selected = []
    for name in names:
        tool = by_name.get(name)
        if tool and tool not in selected:
            selected.append(tool)
        if len(selected) == limit:
            break
    return selected


def _apply_keep(selected: list[Tool], tools: list[Tool], keep_names: tuple[str, ...], limit: int) -> list[Tool]:
    if not keep_names:
        return selected[:limit]

    by_name = {tool.name: tool for tool in tools}
    kept = [by_name[name] for name in keep_names if name in by_name]
    kept_names = {tool.name for tool in kept}
    merged = kept + [tool for tool in selected if tool.name not in kept_names]
    return merged[:limit]


def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
