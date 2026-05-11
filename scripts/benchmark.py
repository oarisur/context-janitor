from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_janitor.metrics import estimate_metrics, estimate_tokens  # noqa: E402
from context_janitor.models import load_tools  # noqa: E402
from context_janitor.selection import select_resilient  # noqa: E402


INTENTS = [
    ("github_search_issues", "Find open GitHub issues about {topic}"),
    ("github_create_pr", "Open a pull request for the {topic} branch"),
    ("calendar_create_event", "Schedule a meeting about {topic} tomorrow"),
    ("gmail_send_email", "Email the team about {topic}"),
    ("web_search", "Search the web for current information about {topic}"),
    ("pdf_extract_text", "Extract and summarize text from the {topic} PDF"),
    ("stripe_create_checkout", "Create a Stripe checkout link for {topic}"),
    ("postgres_query", "Run a Postgres query for {topic} records"),
    ("github_search_issues", "Triage repo bugs related to {topic}"),
    ("web_search", "Look up sources for a report on {topic}"),
]

TOPICS = [
    "authentication",
    "billing",
    "daily logs",
    "customer onboarding",
    "latency",
    "database migrations",
    "release notes",
    "security review",
    "pricing",
    "support escalation",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Context Janitor provider modes.")
    parser.add_argument("--tools", default=str(ROOT / "examples" / "tools.json"))
    parser.add_argument("--providers", nargs="+", default=["heuristic"])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout-ms", type=int, default=800)
    parser.add_argument("--openai-model")
    parser.add_argument("--anthropic-model")
    parser.add_argument("--gemini-model")
    parser.add_argument("--router-price-per-million", type=float, default=0.15)
    parser.add_argument("--payload-price-per-million", type=float, default=5.0)
    parser.add_argument(
        "--agent-success-file",
        help="Optional JSON file mapping benchmark modes to measured agent success rates.",
    )
    args = parser.parse_args()

    tools = load_tools(_read_json(args.tools))
    dataset = _dataset()
    agent_success = _read_agent_success(args.agent_success_file)
    rows = [_baseline_row(tools, dataset, agent_success, args.payload_price_per_million)]
    for provider in args.providers:
        model = _model_for(provider, args)
        if provider != "heuristic" and not _has_key(provider):
            rows.append(
                {
                    "mode": provider,
                    "selection_accuracy": "skipped",
                    "agent_success": _agent_success(agent_success, provider),
                    "median_ms": "-",
                    "p95_ms": "-",
                    "router_cost": "-",
                    "payload_cost": "-",
                    "compression": "-",
                    "notes": "missing API key",
                }
            )
            continue
        stats = _run_provider(
            provider,
            model,
            tools,
            dataset,
            args.limit,
            args.timeout_ms,
            args.router_price_per_million,
            args.payload_price_per_million,
        )
        rows.append(
            {
                "mode": provider,
                "selection_accuracy": f"{stats['accuracy']:.1%}",
                "agent_success": _agent_success(agent_success, provider),
                "median_ms": f"{stats['median_ms']:.0f}",
                "p95_ms": f"{stats['p95_ms']:.0f}",
                "router_cost": f"${stats['router_cost']:.6f}",
                "payload_cost": f"${stats['payload_cost']:.6f}",
                "compression": f"{stats['compression']:.1%}",
                "notes": stats["notes"],
            }
        )
    _print_table(rows)
    return 0


def _run_provider(
    provider,
    model,
    tools,
    dataset,
    limit,
    timeout_ms,
    router_price_per_million,
    payload_price_per_million,
):
    durations = []
    correct = 0
    fallbacks = 0
    costs = []
    payload_costs = []
    compression = []
    misses = []
    for item in dataset:
        started = perf_counter()
        result = select_resilient(
            provider=provider,
            model=model,
            prompt=item["prompt"],
            tools=tools,
            limit=limit,
            timeout_ms=timeout_ms,
            fallback="heuristic",
            cache_enabled=False,
        )
        durations.append((perf_counter() - started) * 1000)
        names = {tool.name for tool in result.selected}
        is_correct = item["expected"] in names
        correct += int(is_correct)
        if not is_correct and len(misses) < 3:
            misses.append(f"{item['expected']} -> {', '.join(tool.name for tool in result.selected[:2])}")
        fallbacks += int(result.fallback_used)
        costs.append(
            _router_cost(item["prompt"], tools, provider, router_price_per_million)
        )
        metrics = estimate_metrics(tools, result.selected)
        payload_costs.append(_payload_cost(metrics.selected_tokens, payload_price_per_million))
        compression.append(metrics.reduced_tokens / metrics.original_tokens if metrics.original_tokens else 0)
    notes = f"{fallbacks} fallbacks" if fallbacks else "ok"
    if misses:
        notes = f"{notes}; misses: {'; '.join(misses)}"
    return {
        "accuracy": correct / len(dataset),
        "median_ms": statistics.median(durations),
        "p95_ms": statistics.quantiles(durations, n=20)[18],
        "router_cost": statistics.mean(costs),
        "payload_cost": statistics.mean(payload_costs),
        "compression": statistics.mean(compression),
        "notes": notes,
    }


def _baseline_row(tools, dataset, agent_success, price_per_million):
    payload_tokens = estimate_tokens(json.dumps([tool.raw for tool in tools], separators=(",", ":")))
    return {
        "mode": "No Janitor (baseline)",
        "selection_accuracy": "100.0%",
        "agent_success": _agent_success(agent_success, "baseline"),
        "median_ms": "0",
        "p95_ms": "0",
        "router_cost": "$0.000000",
        "payload_cost": f"${_payload_cost(payload_tokens, price_per_million):.6f}",
        "compression": "0.0%",
        "notes": f"all {len(tools)} tools sent for {len(dataset)} prompts",
    }


def _dataset():
    rows = []
    for expected, template in INTENTS:
        for topic in TOPICS:
            rows.append({"prompt": template.format(topic=topic), "expected": expected})
    return rows


def _model_for(provider, args):
    return {
        "openai": args.openai_model,
        "anthropic": args.anthropic_model,
        "gemini": args.gemini_model,
    }.get(provider)


def _has_key(provider):
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
    }.get(provider, True)


def _router_cost(prompt, tools, provider, price_per_million):
    if provider == "heuristic":
        return 0.0
    payload = {
        "user_prompt": prompt,
        "available_tools": [{"name": tool.name, "description": tool.description} for tool in tools],
    }
    return estimate_tokens(json.dumps(payload, separators=(",", ":"))) / 1_000_000 * price_per_million


def _payload_cost(tokens, price_per_million):
    return tokens / 1_000_000 * price_per_million


def _read_agent_success(path):
    if not path:
        return {}
    payload = _read_json(path)
    return payload if isinstance(payload, dict) else {}


def _agent_success(values, mode):
    value = values.get(mode)
    if value is None:
        return "not measured"
    if isinstance(value, str):
        return value
    return f"{float(value):.1%}"


def _print_table(rows):
    headers = [
        "Mode",
        "Selection accuracy",
        "Agent success",
        "Median ms",
        "p95 ms",
        "Router cost/run",
        "Tool payload/run",
        "Compression",
        "Notes",
    ]
    keys = [
        "mode",
        "selection_accuracy",
        "agent_success",
        "median_ms",
        "p95_ms",
        "router_cost",
        "payload_cost",
        "compression",
        "notes",
    ]
    widths = [
        max(len(header), *(len(str(row[key])) for row in rows))
        for header, key in zip(headers, keys)
    ]
    divider = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    print(divider)
    print("| " + " | ".join(header.ljust(width) for header, width in zip(headers, widths)) + " |")
    print(divider)
    for row in rows:
        print("| " + " | ".join(str(row[key]).ljust(width) for key, width in zip(keys, widths)) + " |")
    print(divider)


def _read_json(path):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
