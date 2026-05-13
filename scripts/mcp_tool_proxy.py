from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_janitor.models import load_tools, raw_tools  # noqa: E402
from context_janitor.selection import select_resilient  # noqa: E402


def main() -> int:
    args = _parse_args()
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


def run_proxy(args: argparse.Namespace, prompt: str, command: list[str]) -> int:
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("Could not open downstream MCP server pipes.")
    server_stdin = process.stdin
    server_stdout = process.stdout

    pending_tools_list: set[Any] = set()
    lock = threading.Lock()

    def client_to_server() -> None:
        try:
            for line in sys.stdin:
                message = _parse_json_line(line)
                if isinstance(message, dict) and message.get("method") == "tools/list":
                    with lock:
                        pending_tools_list.add(message.get("id"))
                server_stdin.write(line)
                server_stdin.flush()
        finally:
            server_stdin.close()

    def server_to_client() -> None:
        for line in server_stdout:
            message = _parse_json_line(line)
            if isinstance(message, dict):
                with lock:
                    should_prune = message.get("id") in pending_tools_list
                    pending_tools_list.discard(message.get("id"))
                if should_prune:
                    message = prune_tools_list_response(
                        message,
                        prompt=prompt,
                        limit=args.limit,
                        provider=args.provider,
                        model=args.model,
                        fallback=args.fallback,
                        timeout_ms=args.timeout_ms,
                    )
                    line = json.dumps(message, separators=(",", ":")) + "\n"
            sys.stdout.write(line)
            sys.stdout.flush()

    threads = [
        threading.Thread(target=client_to_server, daemon=True),
        threading.Thread(target=server_to_client, daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return process.wait()


def prune_tools_list_response(
    message: dict[str, Any],
    prompt: str,
    limit: int,
    provider: str = "heuristic",
    model: str | None = None,
    fallback: str = "heuristic",
    timeout_ms: int = 800,
) -> dict[str, Any]:
    result = message.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
        return message

    tools = load_tools(result["tools"])
    selected = select_resilient(
        provider=provider,
        prompt=prompt,
        tools=tools,
        limit=limit,
        model=model,
        fallback=fallback,
        timeout_ms=timeout_ms,
    )
    return {
        **message,
        "result": {
            **result,
            "tools": raw_tools(selected.selected),
            "_janitor": {
                "original_tools": len(tools),
                "selected_tools": len(selected.selected),
                "provider": selected.provider,
                "fallback_used": selected.fallback_used,
            },
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Proxy an MCP stdio server and prune tools/list responses with Context Janitor."
    )
    parser.add_argument("--prompt", help="Task prompt used to rank downstream MCP tools.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--provider", choices=["heuristic", "openai", "anthropic", "gemini"], default="heuristic")
    parser.add_argument("--model")
    parser.add_argument("--fallback", choices=["heuristic", "none"], default="heuristic")
    parser.add_argument("--timeout-ms", type=int, default=800)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Downstream MCP server command after --.")
    return parser.parse_args()


def _parse_json_line(line: str) -> Any:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
