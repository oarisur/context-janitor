import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class EvaluateTest(unittest.TestCase):
    def test_evaluate_outputs_accuracy_for_json_cases(self):
        root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                "scripts/evaluate.py",
                "--tools",
                "examples/tools.json",
                "--evals",
                "examples/evals.example.json",
                "--providers",
                "heuristic",
                "--limit",
                "2",
                "--format",
                "json",
            ],
            check=True,
            capture_output=True,
            cwd=root,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["cases"], 8)
        self.assertEqual(payload["results"][0]["provider"], "heuristic")
        self.assertGreaterEqual(payload["results"][0]["accuracy"], 0.75)

    def test_evaluate_accepts_jsonl_cases(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            evals_path = Path(temp_dir) / "evals.jsonl"
            evals_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "prompt": "Search the public web for release notes",
                                "expected": "web_search",
                            }
                        ),
                        json.dumps(
                            {
                                "prompt": "Create a calendar event for tomorrow",
                                "expected": ["calendar_create_event"],
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluate.py",
                    "--tools",
                    "examples/tools.json",
                    "--evals",
                    str(evals_path),
                    "--providers",
                    "heuristic",
                    "--limit",
                    "1",
                    "--format",
                    "json",
                ],
                check=True,
                capture_output=True,
                cwd=root,
                text=True,
            )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["cases"], 2)


if __name__ == "__main__":
    unittest.main()
