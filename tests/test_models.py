import unittest

from context_janitor.models import load_tools, raw_tools


class LoadToolsTest(unittest.TestCase):
    def test_load_tools_accepts_plain_tools(self):
        tools = load_tools([{"name": "web_search", "description": "Search the web."}])

        self.assertEqual(tools[0].name, "web_search")
        self.assertEqual(tools[0].description, "Search the web.")

    def test_load_tools_accepts_openai_function_tools(self):
        payload = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web.",
                    "parameters": {"type": "object"},
                },
            }
        ]

        tools = load_tools(payload)

        self.assertEqual(tools[0].name, "web_search")
        self.assertEqual(raw_tools(tools), payload)

    def test_load_tools_requires_names(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            load_tools([{"description": "No name"}])

if __name__ == "__main__":
    unittest.main()
