from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from .config import JanitorConfig, load_config, merge_config
from .models import load_tools, raw_tools
from .providers import ProviderError
from .ranker import explain_tools
from .selection import SelectionResult, select_resilient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="context-janitor",
        description="Prune a large LLM tool catalog down to the most relevant tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prune = subparsers.add_parser("prune", help="Select tools for a prompt.")
    prune.add_argument("--prompt", help="User prompt. If omitted, stdin is used.")
    prune.add_argument("--tools", required=True, help="Path to a JSON tool catalog.")
    _add_common_options(prune)
    prune.add_argument(
        "--format",
        default=None,
        choices=["json", "names", "raw"],
        help="Output format. 'raw' returns original tool objects.",
    )
    prune.set_defaults(func=_prune)

    middleware = subparsers.add_parser(
        "middleware",
        help="Read an OpenAI-compatible request JSON from stdin and prune its tools field.",
    )
    _add_common_options(middleware)
    middleware.set_defaults(func=_middleware)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, ProviderError, KeyError, IndexError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _prune(args: argparse.Namespace) -> int:
    config = _resolve_config(args)
    logger = _setup_logging(config.log_level)
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    with open(args.tools, encoding="utf-8") as handle:
        tools = load_tools(json.load(handle))

    result = select_resilient(
        config.provider,
        prompt,
        tools,
        config.limit,
        config.model,
        config.fallback,
        config.timeout_ms,
        config.cache,
        logger,
        config.price_per_million_tokens,
        config.keep,
    )
    _log_metrics(logger, result)
    _write_output(result, tools, config, prompt, args.explain)
    return 0


def _middleware(args: argparse.Namespace) -> int:
    config = _resolve_config(args)
    logger = _setup_logging(config.log_level)
    payload = json.load(sys.stdin)
    tools = load_tools(payload.get("tools", []))
    prompt = _prompt_from_messages(payload.get("messages", []))
    result = select_resilient(
        config.provider,
        prompt,
        tools,
        config.limit,
        config.model,
        config.fallback,
        config.timeout_ms,
        config.cache,
        logger,
        config.price_per_million_tokens,
        config.keep,
    )
    _log_metrics(logger, result)
    if args.dry_run:
        _log_dry_run(logger, tools, result)
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    payload["tools"] = raw_tools(result.selected)
    if args.explain:
        payload["_janitor"] = {"explain": _explain_payload(prompt, tools, config.limit)}
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _write_output(
    result: SelectionResult,
    tools: list[Any],
    config: JanitorConfig,
    prompt: str,
    explain: bool = False,
) -> None:
    if config.format == "names":
        for tool in result.selected:
            print(tool.name)
        if explain:
            _write_explain_stderr(prompt, tools, config.limit)
        return

    if config.format == "raw":
        json.dump(raw_tools(result.selected), sys.stdout, indent=2)
        sys.stdout.write("\n")
        if explain:
            _write_explain_stderr(prompt, tools, config.limit)
        return

    payload = {
        "selected": [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in result.selected
        ],
        "metadata": {
            "requested_provider": result.requested_provider,
            "provider": result.provider,
            "fallback_used": result.fallback_used,
            "cache_hit": result.cache_hit,
            "duration_ms": result.duration_ms,
            "limit": config.limit,
            "available_tools": len(tools),
            "original_tokens": result.metrics.original_tokens,
            "selected_tokens": result.metrics.selected_tokens,
            "reduced_tokens": result.metrics.reduced_tokens,
            "estimated_savings_usd": round(result.metrics.estimated_savings_usd, 6),
        },
    }
    if result.warning:
        payload["metadata"]["warning"] = result.warning
    if explain:
        payload["explain"] = _explain_payload(prompt, tools, config.limit)
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="Path to .janitor.yaml. Defaults to searching upward from cwd.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of tools to keep.")
    parser.add_argument(
        "--provider",
        default=None,
        choices=["heuristic", "openai", "anthropic", "gemini"],
        help="Selection backend.",
    )
    parser.add_argument("--model", default=None, help="Model name for API-backed providers.")
    parser.add_argument(
        "--fallback",
        default=None,
        choices=["heuristic", "none"],
        help="Fallback provider to use when an API provider fails.",
    )
    parser.add_argument(
        "--cache",
        default=None,
        action=argparse.BooleanOptionalAction,
        help="Use ~/.janitor_cache for exact and near-exact prompt matches.",
    )
    parser.add_argument("--timeout-ms", type=int, default=None, help="Provider call timeout in milliseconds.")
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Structured log level for stderr.",
    )
    parser.add_argument(
        "--price-per-million-tokens",
        type=float,
        default=None,
        help="Input token price used for savings estimates.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Show why tools were kept or pruned.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="For middleware mode, log the pruning decision without modifying the request payload.",
    )
    parser.add_argument(
        "--keep",
        default=None,
        help="Comma-separated tool names that must remain in the selected set.",
    )


def _resolve_config(args: argparse.Namespace) -> JanitorConfig:
    config = load_config(explicit_path=args.config)
    overrides = {
        "provider": getattr(args, "provider", None),
        "model": getattr(args, "model", None),
        "limit": getattr(args, "limit", None),
        "fallback": getattr(args, "fallback", None),
        "cache": getattr(args, "cache", None),
        "timeout_ms": getattr(args, "timeout_ms", None),
        "log_level": getattr(args, "log_level", None),
        "format": getattr(args, "format", None),
        "price_per_million_tokens": getattr(args, "price_per_million_tokens", None),
        "keep": _parse_keep(getattr(args, "keep", None)),
    }
    return merge_config(config, overrides)


def _setup_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("context_janitor")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[Janitor] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper()))
    logger.propagate = False
    return logger


def _log_metrics(logger: logging.Logger, result: SelectionResult) -> None:
    metrics = result.metrics
    logger.info(
        "event=pruned requested_provider=%s provider=%s fallback=%s cache_hit=%s "
        "tools_before=%s tools_after=%s tokens_before=%s tokens_after=%s "
        "tokens_saved=%s estimated_savings_usd=%.6f duration_ms=%s",
        result.requested_provider,
        result.provider,
        str(result.fallback_used).lower(),
        str(result.cache_hit).lower(),
        metrics.original_tools,
        metrics.selected_tools,
        metrics.original_tokens,
        metrics.selected_tokens,
        metrics.reduced_tokens,
        metrics.estimated_savings_usd,
        result.duration_ms,
    )


def _log_dry_run(logger: logging.Logger, tools: list[Any], result: SelectionResult) -> None:
    selected_names = {tool.name for tool in result.selected}
    pruned_names = [tool.name for tool in tools if tool.name not in selected_names]
    logger.warning(
        "event=dry_run would_keep=%s would_prune=%s",
        [tool.name for tool in result.selected],
        pruned_names,
    )


def _explain_payload(prompt: str, tools: list[Any], limit: int) -> list[dict[str, Any]]:
    return [
        {
            "name": item.tool.name,
            "selected": item.selected,
            "score": round(item.score, 4),
            "matched_terms": item.matched_terms,
            "top_terms": item.top_terms,
        }
        for item in explain_tools(prompt, tools, limit)
    ]


def _write_explain_stderr(prompt: str, tools: list[Any], limit: int) -> None:
    for item in _explain_payload(prompt, tools, limit):
        status = "kept" if item["selected"] else "pruned"
        terms = ", ".join(item["matched_terms"]) or "none"
        print(
            f"[Janitor] EXPLAIN {status} {item['name']} score={item['score']} matched={terms}",
            file=sys.stderr,
        )


def _parse_keep(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _prompt_from_messages(messages: list[dict[str, Any]]) -> str:
    parts = []
    for message in messages:
        role = message.get("role", "unknown")
        content = message.get("content", "")
        if isinstance(content, str):
            parts.append(f"{role}: {content}")
        elif isinstance(content, list):
            text_parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") in {"text", "input_text"}
            ]
            parts.append(f"{role}: {' '.join(text_parts)}")
    return "\n".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
