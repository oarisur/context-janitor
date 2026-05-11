import os
import unittest
from unittest.mock import patch

from context_janitor.models import Tool
from context_janitor.selection import select_resilient


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


if __name__ == "__main__":
    unittest.main()
