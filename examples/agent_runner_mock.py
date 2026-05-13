from __future__ import annotations

import json
import os
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    max_tools = int(os.environ.get("JANITOR_MOCK_AGENT_MAX_TOOLS", "5"))
    tool_names = {_tool_name(tool) for tool in payload.get("tools", [])}
    expected = set(payload.get("expected_tools", []))
    success = expected <= tool_names and len(tool_names) <= max_tools
    json.dump(
        {
            "success": success,
            "used_tools": sorted(expected & tool_names),
            "tool_count": len(tool_names),
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


def _tool_name(tool):
    if isinstance(tool, dict) and isinstance(tool.get("function"), dict):
        return tool["function"].get("name")
    if isinstance(tool, dict):
        return tool.get("name")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
