import tempfile
import unittest
from pathlib import Path

from context_janitor.config import load_config


class ConfigTest(unittest.TestCase):
    def test_load_config_reads_flat_yaml(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".janitor.yaml"
            path.write_text(
                "\n".join(
                    [
                        "provider: anthropic",
                        "model: claude-3-haiku-20240307",
                        "limit: 3",
                        "fallback: heuristic",
                        "cache: true",
                        "timeout_ms: 700",
                        "log_level: INFO",
                        "keep: log_error,notify_admin",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(explicit_path=str(path))

        self.assertEqual(config.provider, "anthropic")
        self.assertEqual(config.model, "claude-3-haiku-20240307")
        self.assertEqual(config.limit, 3)
        self.assertTrue(config.cache)
        self.assertEqual(config.timeout_ms, 700)
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.keep, ("log_error", "notify_admin"))

    def test_load_config_reads_alias_section(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".janitor.yaml"
            path.write_text(
                "\n".join(
                    [
                        "aliases:",
                        "  bq: bigquery,query,warehouse",
                        "  blast: email,send",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(explicit_path=str(path))

        self.assertEqual(config.aliases["bq"], ("bigquery", "query", "warehouse"))
        self.assertEqual(config.aliases["blast"], ("email", "send"))

    def test_load_config_normalizes_case(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".janitor.yaml"
            path.write_text("provider: OpenAI\nfallback: Heuristic\nlog_level: info\nformat: Names\n")

            config = load_config(explicit_path=str(path))

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.fallback, "heuristic")
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.format, "names")

    def test_load_config_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".janitor.yaml"
            path.write_text("provider: typo\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "provider"):
                load_config(explicit_path=str(path))

    def test_load_config_rejects_non_positive_limits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".janitor.yaml"
            path.write_text("limit: 0\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "limit"):
                load_config(explicit_path=str(path))


if __name__ == "__main__":
    unittest.main()
