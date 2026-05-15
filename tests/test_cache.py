import json
import tempfile
import unittest
from pathlib import Path

from context_janitor.cache import MAX_CACHE_BYTES, cache_info, get_cached_selection, store_selection
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

    def test_cache_key_includes_prompt_aliases(self):
        tools = [
            Tool("bigquery_run_query", "Run an analytical BigQuery SQL query."),
            Tool("gmail_send", "Send email."),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            store_selection(
                "pull bq numbers",
                tools,
                [tools[0]],
                "heuristic",
                None,
                1,
                cache_path,
                prompt_aliases={"bq": ("bigquery", "query")},
            )

            entry_without_aliases = get_cached_selection(
                "pull bq numbers",
                tools,
                "heuristic",
                None,
                1,
                cache_path,
            )
            entry_with_aliases = get_cached_selection(
                "pull bq numbers",
                tools,
                "heuristic",
                None,
                1,
                cache_path,
                prompt_aliases={"bq": ("bigquery", "query")},
            )

        self.assertIsNone(entry_without_aliases)
        self.assertIsNotNone(entry_with_aliases)

    def test_oversized_cache_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            cache_path.write_text("{" + (" " * MAX_CACHE_BYTES) + "}", encoding="utf-8")

            info = cache_info(cache_path)

        self.assertTrue(info["exists"])
        self.assertEqual(info["entries"], 0)

    def test_cached_prompt_preview_is_truncated(self):
        tools = [Tool("web_search", "Search the public web.")]
        prompt = "x" * 25_000
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            store_selection(prompt, tools, tools, "heuristic", None, 1, cache_path)

            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_prompt = next(iter(payload.values()))["prompt"]

        self.assertEqual(len(cached_prompt), 20_000)


if __name__ == "__main__":
    unittest.main()
