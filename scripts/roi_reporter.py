from __future__ import annotations

import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_janitor.models import load_tools  # noqa: E402
from context_janitor.selection import select_resilient  # noqa: E402


ALL_TOOLS = [
    {"name": "github_search", "description": "Search issues and pull requests."},
    {"name": "github_create_pr", "description": "Open a pull request."},
    {"name": "db_query", "description": "Run SQL on postgres."},
    {"name": "send_email", "description": "Send a message via Gmail."},
    {"name": "slack_msg", "description": "Post a message to a Slack channel."},
] + [{"name": f"junk_tool_{i}", "description": f"Irrelevant task {i}."} for i in range(45)]

PROMPTS = [
    "Find github issues about auth",
    "Query the database for users",
    "Send an email to support",
    "Message the team on slack",
]


def run_report(runs: int = 100) -> None:
    print(f"Running ROI Simulation ({runs} requests)...")
    tools = load_tools(ALL_TOOLS)
    total_saved_usd = 0.0
    total_time_ms = 0.0
    total_tokens_before = 0
    total_tokens_after = 0

    for _ in range(runs):
        prompt = random.choice(PROMPTS)
        started = time.perf_counter()
        result = select_resilient(
            provider="heuristic",
            prompt=prompt,
            tools=tools,
            limit=3,
        )
        total_time_ms += (time.perf_counter() - started) * 1000
        total_tokens_before += result.metrics.original_tokens
        total_tokens_after += result.metrics.selected_tokens
        total_saved_usd += result.metrics.estimated_savings_usd

    reduction = ((total_tokens_before - total_tokens_after) / total_tokens_before) * 100

    print("\n" + "=" * 45)
    print("   CONTEXT JANITOR FINANCIAL REPORT")
    print("=" * 45)
    print(f"Total Requests:     {runs}")
    print(f"Token Reduction:    {reduction:.1f}%")
    print(f"Avg. Latency:       {total_time_ms / runs:.2f} ms")
    print(f"Total USD Saved:    ${total_saved_usd:.4f}")
    print("=" * 45)


if __name__ == "__main__":
    run_report()
