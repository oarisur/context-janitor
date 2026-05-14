from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_janitor.mcp_proxy import prune_tools_list_response, run_proxy  # noqa: E402,F401


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


if __name__ == "__main__":
    raise SystemExit(main())
