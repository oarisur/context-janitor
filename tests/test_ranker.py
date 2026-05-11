import unittest

from context_janitor.models import Tool
from context_janitor.ranker import select_tools


class SelectToolsTest(unittest.TestCase):
    def test_select_tools_prefers_matching_descriptions(self):
        tools = [
            Tool("calendar_create_event", "Create calendar events."),
            Tool("github_search_issues", "Search GitHub issues by label and state."),
            Tool("stripe_checkout", "Create payment checkout sessions."),
        ]

        selected = select_tools("Find open GitHub issues about auth", tools, limit=1)

        self.assertEqual([tool.name for tool in selected], ["github_search_issues"])

    def test_select_tools_returns_original_when_catalog_is_under_limit(self):
        tools = [Tool("one"), Tool("two")]

        self.assertEqual(select_tools("anything", tools, limit=5), tools)

if __name__ == "__main__":
    unittest.main()
