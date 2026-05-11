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


if __name__ == "__main__":
    unittest.main()
