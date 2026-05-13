import subprocess
import sys
import unittest
from pathlib import Path


class RoiReporterTest(unittest.TestCase):
    def test_roi_reporter_runs(self):
        result = subprocess.run(
            [sys.executable, "scripts/roi_reporter.py"],
            check=True,
            capture_output=True,
            cwd=Path(__file__).resolve().parents[1],
            text=True,
        )

        self.assertIn("CONTEXT JANITOR FINANCIAL REPORT", result.stdout)
        self.assertIn("Token Reduction", result.stdout)


if __name__ == "__main__":
    unittest.main()
