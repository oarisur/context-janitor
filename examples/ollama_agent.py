from __future__ import annotations

import json
import time
from typing import Any

from context_janitor.models import load_tools
from context_janitor.selection import select_resilient


MODEL = "qwen2.5-coder:3b-instruct-q4_K_M"
PROMPT = "Can you tell me the weather in Tokyo?"


def build_catalog() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a specific city.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]

    for index in range(20):
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"legacy_system_{index}",
                    "description": f"Do not use. Internal legacy tool {index}.",
                },
            }
        )

    return tools


def extract_native_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for tool_call in message.get("tool_calls") or []:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        if not isinstance(function, dict):
            continue
        normalized = _normalize_tool_call(function)
        if normalized is not None:
            calls.append(normalized)
    return calls


def coerce_message(response: Any) -> dict[str, Any] | None:
    response_data = _as_plain_dict(response)
    if response_data is not None:
        message = response_data.get("message")
    else:
        message = getattr(response, "message", None)
    return _as_plain_dict(message)


def parse_text_tool_call(content: str) -> dict[str, Any] | None:
    for candidate in _json_candidates(content):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        normalized = _normalize_tool_call(parsed)
        if normalized is not None:
            return normalized
    return None


def _json_candidates(content: str) -> list[str]:
    stripped = content.strip()
    candidates: list[str] = []

    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        fenced = "\n".join(lines).strip()
        if fenced:
            candidates.append(fenced)

    if stripped:
        candidates.append(stripped)

    extracted = _extract_first_json_object(stripped)
    if extracted:
        candidates.append(extracted)

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _as_plain_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped

    result: dict[str, Any] = {}
    for key in ("role", "content", "tool_calls"):
        if hasattr(value, key):
            result[key] = getattr(value, key)
    return result or None


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _normalize_tool_call(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    name = value.get("name")
    arguments = value.get("arguments", {})

    if not isinstance(name, str) or not name:
        return None

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"raw": arguments}

    if arguments is None:
        arguments = {}
    elif not isinstance(arguments, dict):
        arguments = {"value": arguments}

    return {"name": name, "arguments": arguments}


def run_agent() -> int:
    try:
        import ollama
    except ImportError:
        print("Error: install the optional Ollama client with `pip install ollama`.")
        return 1

    tools = build_catalog()

    print("1. Context Janitor is pruning the catalog...")
    start_janitor = time.perf_counter()
    result = select_resilient(
        provider="heuristic",
        prompt=PROMPT,
        tools=load_tools(tools),
        limit=2,
    )
    janitor_ms = (time.perf_counter() - start_janitor) * 1000

    kept_tool_names = [tool.name for tool in result.selected]
    pruned_tools = [tool for tool in tools if tool["function"]["name"] in kept_tool_names]

    print(f"Pruned from {len(tools)} tools down to {len(pruned_tools)} in {janitor_ms:.2f}ms.")
    print(f"Kept: {kept_tool_names}\n")

    print(f"2. Sending prompt and pruned tools to Ollama ({MODEL})...")
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT}],
            tools=pruned_tools,
        )
    except Exception as error:
        print(f"\nError calling Ollama: {error}")
        return 1

    message = coerce_message(response)
    if message is None:
        print(f"\nUnexpected Ollama response: {response}")
        return 1

    print("\nOllama Response:")
    native_calls = extract_native_tool_calls(message)
    if native_calls:
        print("STATUS: Native Tool Call Detected")
        _print_tool_calls(native_calls)
        return 0

    content = str(message.get("content") or "")
    parsed_call = parse_text_tool_call(content)
    if parsed_call is not None:
        print("STATUS: Manual JSON Fallback Triggered")
        _print_tool_calls([parsed_call])
        return 0

    print("STATUS: Plain Text Response")
    print(f"-> Content: {content}")
    return 0


def _print_tool_calls(calls: list[dict[str, Any]]) -> None:
    for call in calls:
        print(f"-> Tool: {call['name']}")
        print(f"-> Args: {call['arguments']}")


if __name__ == "__main__":
    raise SystemExit(run_agent())
