import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PrepareEvalsTest(unittest.TestCase):
    def test_prepare_evals_creates_cases_from_jsonl_logs(self):
        root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                "scripts/prepare_evals.py",
                "--logs",
                "examples/agent_logs.example.jsonl",
                "--success-field",
                "success",
            ],
            check=True,
            capture_output=True,
            cwd=root,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["metadata"]["records"], 4)
        self.assertEqual(payload["metadata"]["cases"], 3)
        self.assertEqual(payload["metadata"]["skipped"], 1)
        self.assertEqual(payload["cases"][0]["expected_tools"], ["github_search_issues"])
        self.assertEqual(payload["cases"][1]["expected_tools"], ["github_create_pr"])
        self.assertEqual(payload["cases"][2]["expected_tools"], ["calendar_create_event"])

    def test_prepare_evals_supports_nested_fields_and_output_file(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_path = Path(temp_dir) / "logs.json"
            output_path = Path(temp_dir) / "drafts" / "evals.json"
            logs_path.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "trace": {"id": "nested-1"},
                                "input": {"prompt": "Search the web for release notes"},
                                "chosen": {"tool_name": "web_search"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    "scripts/prepare_evals.py",
                    "--logs",
                    str(logs_path),
                    "--output",
                    str(output_path),
                    "--prompt-field",
                    "input.prompt",
                    "--tool-field",
                    "chosen",
                    "--id-field",
                    "trace.id",
                ],
                check=True,
                capture_output=True,
                cwd=root,
                text=True,
            )

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["cases"][0]["id"], "nested-1")
        self.assertEqual(payload["cases"][0]["expected_tools"], ["web_search"])


if __name__ == "__main__":
    unittest.main()
