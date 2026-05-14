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

    def test_select_tools_expands_common_intent_aliases(self):
        tools = [
            Tool("github_search_issues", "Search GitHub issues by label and state."),
            Tool("calendar_create_event", "Create calendar events with attendees and time."),
        ]

        selected = select_tools("Schedule a meeting tomorrow afternoon", tools, limit=1)

        self.assertEqual([tool.name for tool in selected], ["calendar_create_event"])

    def test_select_tools_handles_messy_operational_synonyms(self):
        tools = [
            Tool("slack_send_message", "Send a Slack message to a channel or user."),
            Tool("calendar_find_availability", "Find open calendar slots across attendees."),
            Tool("s3_upload_file", "Upload a file to Amazon S3 with bucket metadata."),
        ]

        aliases = {
            "archive": ("upload", "file", "s3", "bucket"),
            "ops": ("operations", "s3", "bucket"),
            "storage": ("s3", "bucket", "upload"),
        }

        selected = select_tools("backup archive needs to go into ops storage", tools, limit=1, prompt_aliases=aliases)

        self.assertEqual([tool.name for tool in selected], ["s3_upload_file"])


if __name__ == "__main__":
    unittest.main()
