from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_janitor.config import load_config  # noqa: E402
from context_janitor.models import load_tools  # noqa: E402
from context_janitor.providers import ProviderError  # noqa: E402
from context_janitor.selection import select_resilient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate tool-selection accuracy on real prompts.")
    parser.add_argument("--tools", required=True, help="Path to a JSON tool catalog.")
    parser.add_argument("--evals", required=True, help="Path to JSON or JSONL eval cases.")
    parser.add_argument("--providers", nargs="+", default=["heuristic"])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout-ms", type=int, default=800)
    parser.add_argument("--fallback", choices=["heuristic", "none"], default="heuristic")
    parser.add_argument("--openai-model")
    parser.add_argument("--anthropic-model")
    parser.add_argument("--gemini-model")
    parser.add_argument(
        "--agent-success-file",
        help="Optional JSON map of measured agent success rates by provider.",
    )
    parser.add_argument("--min-accuracy", type=float, help="Fail if any evaluated provider falls below this accuracy.")
    parser.add_argument(
        "--min-distraction-delta",
        type=float,
        help="Fail if any evaluated provider falls below this measured agent-success delta.",
    )
    parser.add_argument("--format", choices=["table", "json"], default="table")
    parser.add_argument("--config", help="Optional .janitor.yaml file for custom prompt aliases.")
    args = parser.parse_args()

    config = load_config(explicit_path=args.config)
    tools = load_tools(_read_json(args.tools))
    cases = _read_cases(args.evals)
    agent_success = _read_agent_success(args.agent_success_file)
    rows = [
        _evaluate_provider(
            provider,
            _model_for(provider, args),
            tools,
            cases,
            args.limit,
            args.timeout_ms,
            args.fallback,
            agent_success,
            config.aliases,
        )
        for provider in args.providers
    ]

    threshold_failures = _threshold_failures(rows, args.min_accuracy, args.min_distraction_delta)

    if args.format == "json":
        json.dump({"cases": len(cases), "results": rows, "threshold_failures": threshold_failures}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_table(rows)
    for failure in threshold_failures:
        print(f"error: {failure}", file=sys.stderr)
    return 1 if threshold_failures else 0


def _evaluate_provider(
    provider: str,
    model: str | None,
    tools: list[Any],
    cases: list[dict[str, Any]],
    limit: int,
    timeout_ms: int,
    fallback: str,
    agent_success: dict[str, Any],
    prompt_aliases: dict[str, tuple[str, ...]],
) -> dict[str, Any]:
    if provider != "heuristic" and not _has_key(provider):
        return _skipped_row(provider, len(cases), "missing API key", agent_success)
    if provider != "heuristic" and not model:
        return _skipped_row(provider, len(cases), "missing model", agent_success)

    correct = 0
    fallbacks = 0
    misses = []
    for case in cases:
        expected = _expected_tools(case)
        try:
            result = select_resilient(
                provider=provider,
                model=model,
                prompt=str(case["prompt"]),
                tools=tools,
                limit=limit,
                timeout_ms=timeout_ms,
                fallback=fallback,
                cache_enabled=False,
                prompt_aliases=prompt_aliases,
            )
        except ProviderError as error:
            misses.append(_miss(case, expected, [], str(error)))
            continue

        selected = [tool.name for tool in result.selected]
        passed = all(name in selected for name in expected)
        correct += int(passed)
        fallbacks += int(result.fallback_used)
        if not passed and len(misses) < 5:
            misses.append(_miss(case, expected, selected))

    return {
        "provider": provider,
        "cases": len(cases),
        "correct": correct,
        "accuracy": correct / len(cases) if cases else 0,
        "agent_success": _agent_success(agent_success, provider),
        "distraction_delta": _distraction_delta(agent_success, provider),
        "fallbacks": fallbacks,
        "misses": misses,
        "status": "ok",
    }


def _skipped_row(
    provider: str,
    cases: int,
    reason: str,
    agent_success: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "cases": cases,
        "correct": 0,
        "accuracy": None,
        "agent_success": _agent_success(agent_success, provider),
        "distraction_delta": _distraction_delta(agent_success, provider),
        "fallbacks": 0,
        "misses": [],
        "status": f"skipped: {reason}",
    }


def _miss(
    case: dict[str, Any],
    expected: list[str],
    selected: list[str],
    error: str | None = None,
) -> dict[str, Any]:
    payload = {
        "id": case.get("id"),
        "prompt": case["prompt"],
        "expected": expected,
        "selected": selected,
    }
    if error:
        payload["error"] = error
    return payload


def _read_cases(path: str) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        cases = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        payload = _read_json(path)
        if isinstance(payload, dict):
            payload = payload.get("cases", payload.get("evals"))
        cases = payload

    if not isinstance(cases, list):
        raise ValueError("Eval file must contain a list, or an object with a 'cases' list.")
    normalized = [_normalize_case(item, index) for index, item in enumerate(cases)]
    if not normalized:
        raise ValueError("Eval file must contain at least one case.")
    return normalized


def _normalize_case(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"Eval case at index {index} must be an object.")
    prompt = item.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"Eval case at index {index} is missing a non-empty prompt.")
    expected = _expected_tools(item)
    if not expected:
        raise ValueError(f"Eval case at index {index} is missing expected tools.")
    return {**item, "prompt": prompt, "expected_tools": expected}


def _expected_tools(case: dict[str, Any]) -> list[str]:
    value = case.get("expected_tools", case.get("expected_tool", case.get("expected")))
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _model_for(provider: str, args: argparse.Namespace) -> str | None:
    return {
        "openai": args.openai_model,
        "anthropic": args.anthropic_model,
        "gemini": args.gemini_model,
    }.get(provider)


def _has_key(provider: str) -> bool:
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
    }.get(provider, True)


def _read_agent_success(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = _read_json(path)
    return payload if isinstance(payload, dict) else {}


def _agent_success(values: dict[str, Any], provider: str) -> float | None:
    value = values.get(provider)
    if value is None:
        return None
    return float(value)


def _distraction_delta(values: dict[str, Any], provider: str) -> float | None:
    baseline = values.get("baseline")
    provider_success = values.get(provider)
    if baseline is None or provider_success is None:
        return None
    return float(provider_success) - float(baseline)


def _print_table(rows: list[dict[str, Any]]) -> None:
    headers = [
        "Provider",
        "Cases",
        "Correct",
        "Accuracy",
        "Agent success",
        "Distraction Delta",
        "Fallbacks",
        "Status",
        "Misses",
    ]
    keys = [
        "provider",
        "cases",
        "correct",
        "accuracy",
        "agent_success",
        "distraction_delta",
        "fallbacks",
        "status",
        "misses",
    ]
    display_rows = []
    for row in rows:
        display_rows.append(
            {
                **row,
                "accuracy": "-" if row["accuracy"] is None else f"{row['accuracy']:.1%}",
                "agent_success": _format_percent(row["agent_success"]),
                "distraction_delta": _format_delta(row["distraction_delta"]),
                "misses": _miss_summary(row["misses"]),
            }
        )
    widths = [
        max(len(header), *(len(str(row[key])) for row in display_rows))
        for header, key in zip(headers, keys)
    ]
    divider = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    print(divider)
    print("| " + " | ".join(header.ljust(width) for header, width in zip(headers, widths)) + " |")
    print(divider)
    for row in display_rows:
        print("| " + " | ".join(str(row[key]).ljust(width) for key, width in zip(keys, widths)) + " |")
    print(divider)


def _threshold_failures(
    rows: list[dict[str, Any]],
    min_accuracy: float | None,
    min_distraction_delta: float | None,
) -> list[str]:
    failures = []
    for row in rows:
        provider = row["provider"]
        accuracy = row["accuracy"]
        if min_accuracy is not None and accuracy is not None and accuracy < min_accuracy:
            failures.append(f"{provider} accuracy {accuracy:.1%} is below minimum {min_accuracy:.1%}")
        delta = row["distraction_delta"]
        if min_distraction_delta is not None and delta is not None and delta < min_distraction_delta:
            failures.append(
                f"{provider} Distraction Delta {delta:.1%} is below minimum {min_distraction_delta:.1%}"
            )
    return failures


def _format_percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def _format_delta(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1%}"


def _miss_summary(misses: list[dict[str, Any]]) -> str:
    if not misses:
        return "-"
    return "; ".join(
        f"{miss.get('id') or miss['prompt']}: expected {','.join(miss['expected'])}"
        for miss in misses[:3]
    )


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
