import time
import json
import random
import sys
from context_janitor.selection import select_resilient
from context_janitor.models import load_tools

# A catalog of 50 tools to simulate a "noisy" environment
all_tools = [
    {"name": "github_search", "description": "Search issues/PRs"},
    {"name": "github_create_pr", "description": "Open a pull request"},
    {"name": "db_query", "description": "Run SQL on postgres"},
    {"name": "send_email", "description": "Send via Gmail"},
    {"name": "slack_msg", "description": "Post to slack channel"}
] + [{"name": f"junk_tool_{i}", "description": f"Irrelevant task {i}"} for i in range(45)]

prompts = [
    "Find github issues about auth",
    "Query the database for users",
    "Send an email to support",
    "Message the team on slack"
]

def run_report(runs=100):
    print(f"📊 Running ROI Simulation ({runs} requests)...")
    total_saved_usd = 0.0
    total_time_ms = 0.0
    total_tokens_before = 0
    total_tokens_after = 0
    
    # 1 Million tokens = $5.00
    PRICE_PER_MILLION = 5.0 

    for _ in range(runs):
        prompt = random.choice(prompts)
        
        start = time.time()
        res = select_resilient(
            provider="heuristic",
            prompt=prompt,
            tools=load_tools(all_tools),
            limit=3
        )
        total_time_ms += (time.time() - start) * 1000

        # Calculate Tokens (Length / 4)
        tokens_before = len(json.dumps(all_tools)) // 4
        # res.selected contains the kept tools
        tokens_after = len(str(res.selected)) // 4 
        
        total_tokens_before += tokens_before
        total_tokens_after += tokens_after

        # Calculate Savings
        saved_tokens = tokens_before - tokens_after
        total_saved_usd += (saved_tokens / 1_000_000) * PRICE_PER_MILLION

    print("\n" + "="*45)
    print(f"   CONTEXT JANITOR FINANCIAL REPORT")
    print("="*45)
    print(f"Total Requests:     {runs}")
    print(f"Token Reduction:    {((total_tokens_before - total_tokens_after)/total_tokens_before)*100:.1f}%")
    print(f"Avg. Latency:       {total_time_ms/runs:.2f} ms")
    print(f"Total USD Saved:    ${total_saved_usd:.4f}")
    print("="*45)

if __name__ == "__main__":
    run_report()