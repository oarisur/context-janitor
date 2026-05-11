import subprocess
import sys
import unittest
from pathlib import Path


class BenchmarkTest(unittest.TestCase):
    def test_benchmark_outputs_baseline_and_heuristic_rows(self):
        result = subprocess.run(
            [sys.executable, "scripts/benchmark.py", "--providers", "heuristic"],
            check=True,
            capture_output=True,
            cwd=Path(__file__).resolve().parents[1],
            text=True,
        )

        self.assertIn("No Janitor (baseline)", result.stdout)
        self.assertIn("heuristic", result.stdout)
        self.assertIn("97.0%", result.stdout)
        self.assertIn("Compression", result.stdout)


if __name__ == "__main__":
    unittest.main()
