from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "examples" / "ollama_agent.py"

spec = importlib.util.spec_from_file_location("ollama_agent", MODULE_PATH)
assert spec is not None
assert spec.loader is not None
ollama_agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ollama_agent)


def test_parse_text_tool_call_accepts_plain_json() -> None:
    call = ollama_agent.parse_text_tool_call(
        '{"name": "get_weather", "arguments": {"city": "Tokyo"}}'
    )

    assert call == {"name": "get_weather", "arguments": {"city": "Tokyo"}}


def test_parse_text_tool_call_accepts_fenced_json() -> None:
    call = ollama_agent.parse_text_tool_call(
        '```json\n{"name": "get_weather", "arguments": {"city": "Tokyo"}}\n```'
    )

    assert call == {"name": "get_weather", "arguments": {"city": "Tokyo"}}


def test_parse_text_tool_call_extracts_json_from_surrounding_text() -> None:
    call = ollama_agent.parse_text_tool_call(
        'The model just replied with text:\n{"name": "get_weather", '
        '"arguments": {"city": "Tokyo"}}'
    )

    assert call == {"name": "get_weather", "arguments": {"city": "Tokyo"}}


def test_parse_text_tool_call_handles_argument_strings() -> None:
    call = ollama_agent.parse_text_tool_call(
        '{"name": "get_weather", "arguments": "{\\"city\\": \\"Tokyo\\"}"}'
    )

    assert call == {"name": "get_weather", "arguments": {"city": "Tokyo"}}


def test_parse_text_tool_call_returns_none_for_malformed_text() -> None:
    assert ollama_agent.parse_text_tool_call("I would call get_weather for Tokyo.") is None


def test_coerce_message_accepts_ollama_response_objects() -> None:
    class Message:
        content = '{"name": "get_weather", "arguments": {"city": "Tokyo"}}'
        tool_calls = None

    class Response:
        message = Message()

    assert ollama_agent.coerce_message(Response()) == {
        "content": '{"name": "get_weather", "arguments": {"city": "Tokyo"}}',
        "tool_calls": None,
    }


def test_coerce_message_prefers_model_dump() -> None:
    class Response:
        def model_dump(self) -> dict[str, object]:
            return {
                "message": {
                    "role": "assistant",
                    "content": '{"name": "get_weather", "arguments": {"city": "Tokyo"}}',
                }
            }

    assert ollama_agent.coerce_message(Response()) == {
        "role": "assistant",
        "content": '{"name": "get_weather", "arguments": {"city": "Tokyo"}}',
    }


def test_extract_native_tool_calls_normalizes_ollama_shape() -> None:
    calls = ollama_agent.extract_native_tool_calls(
        {
            "tool_calls": [
                {
                    "function": {
                        "name": "get_weather",
                        "arguments": {"city": "Tokyo"},
                    }
                }
            ]
        }
    )

    assert calls == [{"name": "get_weather", "arguments": {"city": "Tokyo"}}]
