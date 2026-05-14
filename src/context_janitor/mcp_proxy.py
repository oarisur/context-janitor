from __future__ import annotations

import json
import subprocess
import sys
import threading
from argparse import Namespace
from typing import Any, TextIO

from .models import load_tools, raw_tools
from .selection import select_resilient


def run_proxy(
    args: Namespace,
    prompt: str,
    command: list[str],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr,
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
            for line in stdin:
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
            stdout.write(line)
            stdout.flush()

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


def _parse_json_line(line: str) -> Any:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None
