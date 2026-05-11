from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .models import load_tools, raw_tools
from .providers import ProviderError, select_with_provider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="context-janitor",
        description="Prune a large LLM tool catalog down to the most relevant tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prune = subparsers.add_parser("prune", help="Select tools for a prompt.")
    prune.add_argument("--prompt", help="User prompt. If omitted, stdin is used.")
    prune.add_argument("--tools", required=True, help="Path to a JSON tool catalog.")
    prune.add_argument("--limit", type=int, default=5, help="Maximum number of tools to return.")
    prune.add_argument(
        "--provider",
        default="heuristic",
        choices=["heuristic", "openai", "anthropic", "gemini"],
        help="Selection backend.",
    )
    prune.add_argument("--model", help="Model name for API-backed providers.")
    prune.add_argument(
        "--format",
        default="json",
        choices=["json", "names", "raw"],
        help="Output format. 'raw' returns original tool objects.",
    )
    prune.set_defaults(func=_prune)

    middleware = subparsers.add_parser(
        "middleware",
        help="Read an OpenAI-compatible request JSON from stdin and prune its tools field.",
    )
    middleware.add_argument("--limit", type=int, default=5, help="Maximum number of tools to keep.")
    middleware.add_argument(
        "--provider",
        default="heuristic",
        choices=["heuristic", "openai", "anthropic", "gemini"],
        help="Selection backend.",
    )
    middleware.add_argument("--model", help="Model name for API-backed providers.")
    middleware.set_defaults(func=_middleware)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, ProviderError, KeyError, IndexError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _prune(args: argparse.Namespace) -> int:
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    with open(args.tools, encoding="utf-8") as handle:
        tools = load_tools(json.load(handle))

    selected = select_with_provider(args.provider, prompt, tools, args.limit, args.model)
    _write_output(selected, tools, args)
    return 0


def _middleware(args: argparse.Namespace) -> int:
    payload = json.load(sys.stdin)
    tools = load_tools(payload.get("tools", []))
    prompt = _prompt_from_messages(payload.get("messages", []))
    selected = select_with_provider(args.provider, prompt, tools, args.limit, args.model)
    payload["tools"] = raw_tools(selected)
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _write_output(selected: list[Any], tools: list[Any], args: argparse.Namespace) -> None:
    if args.format == "names":
        for tool in selected:
            print(tool.name)
        return

    if args.format == "raw":
        json.dump(raw_tools(selected), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    payload = {
        "selected": [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in selected
        ],
        "metadata": {
            "provider": args.provider,
            "limit": args.limit,
            "available_tools": len(tools),
        },
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


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
