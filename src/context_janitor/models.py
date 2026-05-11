from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Tool:
    name: str
    description: str = ""
    raw: dict[str, Any] | None = None

    @property
    def searchable_text(self) -> str:
        return f"{self.name} {self.description}".strip()


def load_tools(payload: Any) -> list[Tool]:
    """Normalize common tool catalog shapes into Tool objects."""
    if isinstance(payload, dict):
        if isinstance(payload.get("tools"), list):
            payload = payload["tools"]
        elif isinstance(payload.get("functions"), list):
            payload = payload["functions"]
        else:
            raise ValueError("Expected a list of tools, or an object with a 'tools' list.")

    if not isinstance(payload, list):
        raise ValueError("Expected tools JSON to be a list.")

    tools: list[Tool] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Tool at index {index} must be an object.")
        tools.append(_normalize_tool(item, index))
    return tools


def _normalize_tool(item: dict[str, Any], index: int) -> Tool:
    if item.get("type") == "function" and isinstance(item.get("function"), dict):
        function = item["function"]
        name = _require_name(function, index)
        return Tool(
            name=name,
            description=str(function.get("description", "")),
            raw=item,
        )

    name = _require_name(item, index)
    description = item.get("description", item.get("summary", ""))
    return Tool(name=name, description=str(description), raw=item)


def _require_name(item: dict[str, Any], index: int) -> str:
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Tool at index {index} is missing a non-empty name.")
    return name.strip()


def raw_tools(tools: list[Tool]) -> list[dict[str, Any]]:
    return [tool.raw or {"name": tool.name, "description": tool.description} for tool in tools]
