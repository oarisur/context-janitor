import json
import os
import subprocess
import sys
import unittest


class CliTest(unittest.TestCase):
    def test_prune_cli_outputs_matching_tool(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            tools_path = Path(temp_dir) / "tools.json"
            tools_path.write_text(
                json.dumps(
                    [
                        {"name": "gmail_send", "description": "Send email messages."},
                        {"name": "pdf_extract_text", "description": "Extract text from PDF files."},
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "context_janitor.cli",
                    "prune",
                    "--prompt",
                    "Read this PDF and summarize it",
                    "--tools",
                    str(tools_path),
                    "--limit",
                    "1",
                    "--format",
                    "names",
                ],
                check=True,
                capture_output=True,
                env=_env(),
                text=True,
            )

        self.assertEqual(result.stdout.strip(), "pdf_extract_text")

    def test_middleware_prunes_tools(self):
        request = {
            "messages": [{"role": "user", "content": "Create a calendar event"}],
            "tools": [
                {"type": "function", "function": {"name": "calendar_create", "description": "Create events."}},
                {"type": "function", "function": {"name": "web_search", "description": "Search the web."}},
            ],
        }

        result = subprocess.run(
            [sys.executable, "-m", "context_janitor.cli", "middleware", "--limit", "1"],
            input=json.dumps(request),
            check=True,
            capture_output=True,
            env=_env(),
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["tools"][0]["function"]["name"], "calendar_create")
        self.assertEqual(len(payload["tools"]), 1)


def _env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = os.path.abspath("src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return env


if __name__ == "__main__":
    unittest.main()
