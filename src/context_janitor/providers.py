from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .models import Tool
from .ranker import select_tools


class ProviderError(RuntimeError):
    pass


def select_with_provider(
    provider: str,
    prompt: str,
    tools: list[Tool],
    limit: int,
    model: str | None = None,
) -> list[Tool]:
    provider = provider.lower()
    if provider == "heuristic":
        return select_tools(prompt, tools, limit)
    if provider == "openai":
        names = _select_openai(prompt, tools, limit, model)
    elif provider == "anthropic":
        names = _select_anthropic(prompt, tools, limit, model)
    elif provider == "gemini":
        names = _select_gemini(prompt, tools, limit, model)
    else:
        raise ProviderError(f"Unknown provider '{provider}'.")

    return _tools_by_names(names, tools, limit)


def _select_openai(prompt: str, tools: list[Tool], limit: int, model: str | None) -> list[str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ProviderError("OPENAI_API_KEY is required for --provider openai.")
    if not model:
        raise ProviderError("--model is required for --provider openai.")

    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _system_prompt(limit)},
            {"role": "user", "content": _selection_prompt(prompt, tools, limit)},
        ],
    }
    response = _post_json(
        "https://api.openai.com/v1/chat/completions",
        body,
        {"Authorization": f"Bearer {api_key}"},
    )
    return _extract_names(response["choices"][0]["message"]["content"])


def _select_anthropic(prompt: str, tools: list[Tool], limit: int, model: str | None) -> list[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ProviderError("ANTHROPIC_API_KEY is required for --provider anthropic.")
    if not model:
        raise ProviderError("--model is required for --provider anthropic.")

    body = {
        "model": model,
        "max_tokens": 300,
        "temperature": 0,
        "system": _system_prompt(limit),
        "messages": [{"role": "user", "content": _selection_prompt(prompt, tools, limit)}],
    }
    response = _post_json(
        "https://api.anthropic.com/v1/messages",
        body,
        {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    text = "\n".join(block.get("text", "") for block in response.get("content", []))
    return _extract_names(text)


def _select_gemini(prompt: str, tools: list[Tool], limit: int, model: str | None) -> list[str]:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ProviderError("GEMINI_API_KEY or GOOGLE_API_KEY is required for --provider gemini.")
    if not model:
        raise ProviderError("--model is required for --provider gemini.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "generationConfig": {"temperature": 0},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{_system_prompt(limit)}\n\n{_selection_prompt(prompt, tools, limit)}"}],
            }
        ],
    }
    response = _post_json(url, body, {})
    candidates = response.get("candidates", [])
    text = ""
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts)
    return _extract_names(text)


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise ProviderError(f"Provider request failed with HTTP {error.code}: {message}") from error
    except urllib.error.URLError as error:
        raise ProviderError(f"Provider request failed: {error.reason}") from error


def _system_prompt(limit: int) -> str:
    return (
        "You are Context Janitor. Select only the tool names that are relevant to the user's task. "
        f"Return strict JSON with a single key named selected containing at most {limit} strings. "
        "Do not invent tool names."
    )


def _selection_prompt(prompt: str, tools: list[Tool], limit: int) -> str:
    catalog = [{"name": tool.name, "description": tool.description} for tool in tools]
    return json.dumps(
        {
            "user_prompt": prompt,
            "max_tools": limit,
            "available_tools": catalog,
        },
        indent=2,
    )


def _extract_names(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return re.findall(r"[A-Za-z_][A-Za-z0-9_.:-]*", text)

    if isinstance(payload, dict) and isinstance(payload.get("selected"), list):
        return [str(name) for name in payload["selected"]]
    if isinstance(payload, list):
        return [str(name) for name in payload]
    return []


def _tools_by_names(names: list[str], tools: list[Tool], limit: int) -> list[Tool]:
    by_name = {tool.name: tool for tool in tools}
    selected = []
    for name in names:
        tool = by_name.get(name)
        if tool and tool not in selected:
            selected.append(tool)
        if len(selected) == limit:
            break
    return selected or select_tools(" ".join(names), tools, limit)
