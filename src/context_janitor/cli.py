from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from .cache import cache_info, clear_cache, default_cache_path
from .config import JanitorConfig, find_config, load_config, merge_config
from .models import load_tools, raw_tools
from .mcp_proxy import run_proxy
from .providers import ProviderError
from .ranker import explain_tools
from .selection import SelectionResult, select_resilient

MAX_JSON_INPUT_BYTES = 10 * 1024 * 1024
MAX_STDIN_CHARS = 10 * 1024 * 1024


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
    prune.add_argument(
        "--dry-run",
        action="store_true",
        help="Run selection without reading or writing the local cache.",
    )
    prune.set_defaults(func=_prune)

    middleware = subparsers.add_parser(
        "middleware",
        help="Read an OpenAI-compatible request JSON from stdin and prune its tools field.",
    )
    _add_common_options(middleware)
    middleware.add_argument(
        "--dry-run",
        action="store_true",
        help="Log the pruning decision without modifying the request payload.",
    )
    middleware.set_defaults(func=_middleware)

    mcp_proxy = subparsers.add_parser(
        "mcp-proxy",
        help="Proxy an MCP stdio server and prune tools/list responses.",
        description="Proxy an MCP stdio server and prune tools/list responses with Context Janitor.",
    )
    mcp_proxy.add_argument("--prompt", help="Task prompt used to rank downstream MCP tools.")
    mcp_proxy.add_argument("--config", help="Path to .janitor.yaml for custom prompt aliases.")
    mcp_proxy.add_argument("--limit", type=int, default=5)
    mcp_proxy.add_argument(
        "--provider",
        choices=["heuristic", "openai", "anthropic", "gemini"],
        default="heuristic",
    )
    mcp_proxy.add_argument("--model")
    mcp_proxy.add_argument("--fallback", choices=["heuristic", "none"], default="heuristic")
    mcp_proxy.add_argument("--timeout-ms", type=int, default=800)
    mcp_proxy.add_argument("command", nargs=argparse.REMAINDER, help="Downstream MCP server command after --.")
    mcp_proxy.set_defaults(func=_mcp_proxy)

    lint = subparsers.add_parser("lint", help="Validate a tool catalog and report quality warnings.")
    lint.add_argument("--tools", required=True, help="Path to a JSON tool catalog.")
    lint.add_argument("--format", choices=["text", "json"], default="text")
    lint.set_defaults(func=_lint)

    cache = subparsers.add_parser("clear-cache", help="Delete the local selection cache.")
    cache.add_argument("--cache-path", help="Optional cache file path. Defaults to ~/.janitor_cache/cache.json.")
    cache.set_defaults(func=_clear_cache)

    cache_info_parser = subparsers.add_parser("cache-info", help="Show local selection cache metadata.")
    cache_info_parser.add_argument(
        "--cache-path",
        help="Optional cache file path. Defaults to ~/.janitor_cache/cache.json.",
    )
    cache_info_parser.add_argument("--format", choices=["text", "json"], default="text")
    cache_info_parser.set_defaults(func=_cache_info)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, ProviderError, KeyError, IndexError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _prune(args: argparse.Namespace) -> int:
    config = _resolve_config(args)
    logger = _setup_logging(config.log_level)
    if args.dry_run and config.cache:
        config = replace(config, cache=False)
        logger.warning("event=dry_run cache=false")
    prompt = args.prompt if args.prompt is not None else _read_stdin_text()
    tools = load_tools(_read_json_file(args.tools))

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
        config.aliases,
    )
    _log_metrics(logger, result)
    _write_output(result, tools, config, prompt, args.explain)
    return 0


def _lint(args: argparse.Namespace) -> int:
    tools = load_tools(_read_json_file(args.tools))

    warnings = _lint_warnings(tools)
    payload = {
        "tools": len(tools),
        "warnings": warnings,
        "ok": not warnings,
    }

    if args.format == "json":
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print(f"tools: {len(tools)}")
    if not warnings:
        print("ok: no lint warnings")
        return 0
    for warning in warnings:
        print(f"warning: {warning}")
    return 0


def _clear_cache(args: argparse.Namespace) -> int:
    path = Path(args.cache_path) if args.cache_path else default_cache_path()
    removed = clear_cache(path)
    if removed:
        print(f"cleared cache: {path}")
    else:
        print(f"cache already empty: {path}")
    return 0


def _cache_info(args: argparse.Namespace) -> int:
    path = Path(args.cache_path) if args.cache_path else default_cache_path()
    info = cache_info(path)
    if args.format == "json":
        json.dump(info, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print(f"path: {info['path']}")
    print(f"exists: {str(info['exists']).lower()}")
    print(f"entries: {info['entries']}")
    print(f"providers: {', '.join(info['providers']) or '-'}")
    print(f"models: {', '.join(info['models']) or '-'}")
    print(f"oldest_created_at: {info['oldest_created_at'] or '-'}")
    print(f"newest_created_at: {info['newest_created_at'] or '-'}")
    return 0


def _middleware(args: argparse.Namespace) -> int:
    config = _resolve_config(args)
    logger = _setup_logging(config.log_level)
    payload = _read_stdin_json()
    if not isinstance(payload, dict):
        raise ValueError("middleware input must be a JSON object with optional 'messages' and 'tools' fields.")
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
        config.aliases,
    )
    _log_metrics(logger, result)
    if args.dry_run:
        _log_dry_run(logger, tools, result)
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    payload["tools"] = raw_tools(result.selected)
    if args.explain:
        payload["_janitor"] = {"explain": _explain_payload(prompt, tools, config.limit, config.aliases)}
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _mcp_proxy(args: argparse.Namespace) -> int:
    config = load_config(explicit_path=args.config)
    args.aliases = config.aliases
    prompt = args.prompt or os.environ.get("JANITOR_PROMPT")
    if not prompt:
        print("error: --prompt or JANITOR_PROMPT is required.", file=sys.stderr)
        return 2

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("error: downstream MCP server command is required after --.", file=sys.stderr)
        return 2

    return run_proxy(args, prompt, command)


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
            _write_explain_stderr(prompt, tools, config.limit, config.aliases)
        return

    if config.format == "raw":
        json.dump(raw_tools(result.selected), sys.stdout, indent=2)
        sys.stdout.write("\n")
        if explain:
            _write_explain_stderr(prompt, tools, config.limit, config.aliases)
        return

    payload: dict[str, Any] = {
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
        payload["explain"] = _explain_payload(prompt, tools, config.limit, config.aliases)
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
        "--keep",
        default=None,
        help="Comma-separated tool names that must remain in the selected set.",
    )


def _resolve_config(args: argparse.Namespace) -> JanitorConfig:
    explicit_config = getattr(args, "config", None)
    auto_config = None if explicit_config else find_config(Path.cwd())
    config = load_config(explicit_path=explicit_config)
    if auto_config and getattr(args, "provider", None) is None and config.provider != "heuristic":
        raise ValueError(
            f"auto-discovered config at {auto_config} cannot select network provider "
            f"'{config.provider}'. Pass --config or --provider explicitly if you trust this project."
        )
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


def _read_json_file(path_value: str) -> Any:
    path = Path(path_value)
    size = path.stat().st_size
    if size > MAX_JSON_INPUT_BYTES:
        raise ValueError(
            f"{path} is too large to read as JSON "
            f"({size} bytes; limit is {MAX_JSON_INPUT_BYTES} bytes)."
        )
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_stdin_json() -> Any:
    text = sys.stdin.read(MAX_STDIN_CHARS + 1)
    if len(text) > MAX_STDIN_CHARS:
        raise ValueError(f"stdin JSON is too large; limit is {MAX_STDIN_CHARS} characters.")
    return json.loads(text)


def _read_stdin_text() -> str:
    text = sys.stdin.read(MAX_STDIN_CHARS + 1)
    if len(text) > MAX_STDIN_CHARS:
        raise ValueError(f"stdin prompt is too large; limit is {MAX_STDIN_CHARS} characters.")
    return text


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


def _lint_warnings(tools: list[Any]) -> list[str]:
    warnings = []
    if not tools:
        warnings.append("catalog contains no tools")

    names = [tool.name for tool in tools]
    for name, count in sorted(Counter(names).items()):
        if count > 1:
            warnings.append(f"duplicate tool name '{name}' appears {count} times")

    for tool in tools:
        description = tool.description.strip()
        if not description:
            warnings.append(f"tool '{tool.name}' has an empty description")
        elif len(description) < 12:
            warnings.append(f"tool '{tool.name}' has a very short description")
        elif len(description) > 600:
            warnings.append(f"tool '{tool.name}' has a very long description")
        if _is_generic_name(tool.name):
            warnings.append(f"tool '{tool.name}' has a generic name")
        warnings.extend(_schema_warnings(tool))

    descriptions = [tool.description.strip() for tool in tools if tool.description.strip()]
    for description, count in Counter(descriptions).items():
        if count > 1:
            warnings.append(f"description reused by {count} tools: '{description[:80]}'")
    return warnings


def _is_generic_name(name: str) -> bool:
    generic_terms = {
        "call",
        "create",
        "delete",
        "do",
        "execute",
        "fetch",
        "get",
        "handle",
        "process",
        "query",
        "read",
        "run",
        "search",
        "send",
        "set",
        "tool",
        "update",
        "write",
    }
    terms = [part for part in name.lower().replace("-", "_").split("_") if part]
    return bool(terms) and len(terms) <= 2 and all(term in generic_terms for term in terms)


def _schema_warnings(tool: Any) -> list[str]:
    raw = tool.raw or {}
    warnings = []
    if raw.get("type") == "function" and isinstance(raw.get("function"), dict):
        function = raw["function"]
        parameters = function.get("parameters")
        if parameters is None:
            warnings.append(f"OpenAI function tool '{tool.name}' is missing parameters")
        elif not isinstance(parameters, dict):
            warnings.append(f"OpenAI function tool '{tool.name}' parameters must be an object")

    input_schema = raw.get("inputSchema")
    if input_schema is not None and not isinstance(input_schema, dict):
        warnings.append(f"MCP tool '{tool.name}' inputSchema must be an object")
    return warnings


def _explain_payload(
    prompt: str,
    tools: list[Any],
    limit: int,
    aliases: dict[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "name": item.tool.name,
            "selected": item.selected,
            "score": round(item.score, 4),
            "matched_terms": item.matched_terms,
            "top_terms": item.top_terms,
        }
        for item in explain_tools(prompt, tools, limit, aliases)
    ]


def _write_explain_stderr(
    prompt: str,
    tools: list[Any],
    limit: int,
    aliases: dict[str, tuple[str, ...]] | None = None,
) -> None:
    for item in _explain_payload(prompt, tools, limit, aliases):
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
    if messages is None:
        return ""
    if not isinstance(messages, list):
        raise ValueError("messages must be a list when provided.")

    parts = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"message at index {index} must be an object.")
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
