import os
import json
import unittest
from unittest.mock import patch

from context_janitor.models import Tool
from context_janitor.selection import select_resilient


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps({"unexpected": []}).encode("utf-8")


class SelectionTest(unittest.TestCase):
    def test_provider_failure_falls_back_to_heuristic(self):
        tools = [
            Tool("web_search", "Search the public web."),
            Tool("calendar_create", "Create a calendar event."),
        ]

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            result = select_resilient(
                provider="openai",
                prompt="Find current information on the web",
                tools=tools,
                limit=1,
                model="fast-model",
                fallback="heuristic",
                timeout_ms=1,
            )

        self.assertTrue(result.fallback_used)
        self.assertEqual(result.provider, "heuristic")
        self.assertEqual(result.selected[0].name, "web_search")

    def test_malformed_provider_response_falls_back_to_heuristic(self):
        tools = [
            Tool("web_search", "Search the public web."),
            Tool("calendar_create", "Create a calendar event."),
        ]

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse(),
        ):
            result = select_resilient(
                provider="openai",
                prompt="Find current information on the web",
                tools=tools,
                limit=1,
                model="fast-model",
                fallback="heuristic",
                timeout_ms=1,
            )

        self.assertTrue(result.fallback_used)
        self.assertEqual(result.provider, "heuristic")
        self.assertIn("malformed response", result.warning)

    def test_keep_forces_required_tools_into_selection(self):
        tools = [
            Tool("web_search", "Search the public web."),
            Tool("calendar_create", "Create calendar events."),
            Tool("log_error", "Record safety and error telemetry."),
        ]

        result = select_resilient(
            provider="heuristic",
            prompt="Search the web",
            tools=tools,
            limit=2,
            keep=("log_error",),
        )

        self.assertEqual([tool.name for tool in result.selected], ["log_error", "web_search"])


if __name__ == "__main__":
    unittest.main()
