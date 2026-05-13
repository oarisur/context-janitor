import json
import subprocess
import sys
import unittest
from pathlib import Path


class EvalAgentTest(unittest.TestCase):
    def test_eval_agent_reports_distraction_delta(self):
        root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                "scripts/eval_agent.py",
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
                "--",
                sys.executable,
                "examples/agent_runner_mock.py",
            ],
            check=True,
            capture_output=True,
            cwd=root,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["cases"], 8)
        self.assertEqual(payload["results"][0]["provider"], "baseline")
        self.assertEqual(payload["results"][0]["success_rate"], 0)
        self.assertEqual(payload["results"][1]["provider"], "heuristic")
        self.assertEqual(payload["results"][1]["success_rate"], 1)
        self.assertEqual(payload["results"][1]["distraction_delta"], 1)


if __name__ == "__main__":
    unittest.main()
