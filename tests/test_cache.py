import json
import tempfile
import unittest
from pathlib import Path

from context_janitor.cache import get_cached_selection, store_selection
from context_janitor.models import Tool


class CacheTest(unittest.TestCase):
    def test_cache_serves_similar_prompt(self):
        tools = [
            Tool("pdf_extract_text", "Extract text from PDF files."),
            Tool("gmail_send", "Send email."),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            store_selection(
                "Summarize the daily logs",
                tools,
                [tools[0]],
                "openai",
                "fast-model",
                1,
                cache_path,
            )

            entry = get_cached_selection(
                "Summarize daily logs",
                tools,
                "openai",
                "fast-model",
                1,
                cache_path,
                similarity_threshold=0.5,
            )

        self.assertIsNotNone(entry)
        self.assertEqual(entry.names, ["pdf_extract_text"])

    def test_cache_write_does_not_leave_temp_files(self):
        tools = [
            Tool("pdf_extract_text", "Extract text from PDF files."),
            Tool("gmail_send", "Send email."),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            store_selection("Summarize the daily logs", tools, [tools[0]], "heuristic", None, 1, cache_path)

            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            temp_files = list(Path(temp_dir).glob(".cache.json.*.tmp"))

        self.assertEqual(len(payload), 1)
        self.assertEqual(temp_files, [])


if __name__ == "__main__":
    unittest.main()
