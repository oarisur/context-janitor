import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


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

    def test_cli_falls_back_when_provider_is_unavailable(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            tools_path = Path(temp_dir) / "tools.json"
            tools_path.write_text(
                json.dumps(
                    [
                        {"name": "web_search", "description": "Search the public web."},
                        {"name": "gmail_send", "description": "Send email messages."},
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
                    "--provider",
                    "openai",
                    "--model",
                    "fast-model",
                    "--prompt",
                    "Search the web",
                    "--tools",
                    str(tools_path),
                    "--limit",
                    "1",
                    "--log-level",
                    "INFO",
                ],
                check=True,
                capture_output=True,
                env=_env(),
                text=True,
            )

        payload = json.loads(result.stdout)
        self.assertTrue(payload["metadata"]["fallback_used"])
        self.assertEqual(payload["metadata"]["provider"], "heuristic")
        self.assertIn("fell back to heuristic", result.stderr)

    def test_cli_uses_janitor_yaml(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".janitor.yaml").write_text("limit: 1\nformat: names\n", encoding="utf-8")
            tools_path = root / "tools.json"
            tools_path.write_text(
                json.dumps(
                    [
                        {"name": "calendar_create", "description": "Create calendar events."},
                        {"name": "web_search", "description": "Search the public web."},
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
                    "Create a calendar event",
                    "--tools",
                    str(tools_path),
                ],
                check=True,
                capture_output=True,
                cwd=temp_dir,
                env=_env(),
                text=True,
            )

        self.assertEqual(result.stdout.strip(), "calendar_create")

    def test_cli_explain_includes_matching_terms(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            tools_path = Path(temp_dir) / "tools.json"
            tools_path.write_text(
                json.dumps(
                    [
                        {"name": "github_search_issues", "description": "Search GitHub issues."},
                        {"name": "gmail_send", "description": "Send email messages."},
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
                    "Search GitHub issues",
                    "--tools",
                    str(tools_path),
                    "--limit",
                    "1",
                    "--explain",
                ],
                check=True,
                capture_output=True,
                env=_env(),
                text=True,
            )

        payload = json.loads(result.stdout)
        self.assertIn("explain", payload)
        self.assertEqual(payload["explain"][0]["name"], "github_search_issues")
        self.assertIn("github", payload["explain"][0]["matched_terms"])

    def test_middleware_dry_run_preserves_payload_tools(self):
        request = {
            "messages": [{"role": "user", "content": "Create a calendar event"}],
            "tools": [
                {"type": "function", "function": {"name": "calendar_create", "description": "Create events."}},
                {"type": "function", "function": {"name": "web_search", "description": "Search the web."}},
            ],
        }

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "context_janitor.cli",
                "middleware",
                "--limit",
                "1",
                "--dry-run",
            ],
            input=json.dumps(request),
            check=True,
            capture_output=True,
            env=_env(),
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["tools"]), 2)
        self.assertIn("event=dry_run", result.stderr)


def _env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"]:
        env.pop(key, None)
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return env


if __name__ == "__main__":
    unittest.main()
