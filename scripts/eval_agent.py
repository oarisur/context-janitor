from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_janitor.models import load_tools, raw_tools  # noqa: E402
from context_janitor.selection import select_resilient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure agent success with all tools versus Janitor-pruned tools."
    )
    parser.add_argument("--tools", required=True, help="Path to a JSON tool catalog.")
    parser.add_argument("--evals", required=True, help="Path to JSON or JSONL eval cases.")
    parser.add_argument("--providers", nargs="+", default=["heuristic"])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout-ms", type=int, default=800)
    parser.add_argument("--agent-timeout-ms", type=int, default=30_000)
    parser.add_argument("--fallback", choices=["heuristic", "none"], default="heuristic")
    parser.add_argument("--openai-model")
    parser.add_argument("--anthropic-model")
    parser.add_argument("--gemini-model")
    parser.add_argument(
        "--min-janitor-success-rate",
        type=float,
        help="Fail if any Janitor provider falls below this agent success rate.",
    )
    parser.add_argument(
        "--min-distraction-delta",
        type=float,
        help="Fail if any Janitor provider falls below this success-rate delta versus baseline.",
    )
    parser.add_argument("--format", choices=["table", "json"], default="table")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Agent command after --. It receives each eval payload as JSON on stdin.",
    )
    args = parser.parse_args()

    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        print("error: agent command is required after --.", file=sys.stderr)
        return 2

    tools = load_tools(_read_json(args.tools))
    cases = _read_cases(args.evals)
    baseline = _run_mode(
        mode="baseline",
        provider="baseline",
        command=command,
        cases=cases,
        tool_payloads=[raw_tools(tools) for _ in cases],
        agent_timeout_ms=args.agent_timeout_ms,
    )
    rows = [baseline]

    for provider in args.providers:
        pruned_tools = [
            raw_tools(
                select_resilient(
                    provider=provider,
                    model=_model_for(provider, args),
                    prompt=str(case["prompt"]),
                    tools=tools,
                    limit=args.limit,
                    timeout_ms=args.timeout_ms,
                    fallback=args.fallback,
                    cache_enabled=False,
                ).selected
            )
            for case in cases
        ]
        row = _run_mode(
            mode="janitor",
            provider=provider,
            command=command,
            cases=cases,
            tool_payloads=pruned_tools,
            agent_timeout_ms=args.agent_timeout_ms,
        )
        row["distraction_delta"] = row["success_rate"] - baseline["success_rate"]
        rows.append(row)

    threshold_failures = _threshold_failures(
        rows,
        args.min_janitor_success_rate,
        args.min_distraction_delta,
    )

    if args.format == "json":
        json.dump({"cases": len(cases), "results": rows, "threshold_failures": threshold_failures}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_table(rows)
    for failure in threshold_failures:
        print(f"error: {failure}", file=sys.stderr)
    return 1 if threshold_failures else 0


def _run_mode(
    mode: str,
    provider: str,
    command: list[str],
    cases: list[dict[str, Any]],
    tool_payloads: list[list[dict[str, Any]]],
    agent_timeout_ms: int,
) -> dict[str, Any]:
    successes = 0
    failures: list[dict[str, Any]] = []
    for case, tools in zip(cases, tool_payloads):
        payload = {
            "id": case.get("id"),
            "mode": mode,
            "provider": provider,
            "prompt": case["prompt"],
            "expected_tools": _expected_tools(case),
            "tools": tools,
        }
        result = _run_agent(command, payload, agent_timeout_ms)
        successes += int(result["success"])
        if not result["success"] and len(failures) < 5:
            failures.append(
                {
                    "id": case.get("id"),
                    "prompt": case["prompt"],
                    "expected_tools": payload["expected_tools"],
                    "error": result.get("error"),
                    "stdout": result.get("stdout", "")[:300],
                    "stderr": result.get("stderr", "")[:300],
                }
            )

    return {
        "mode": mode,
        "provider": provider,
        "cases": len(cases),
        "successes": successes,
        "success_rate": successes / len(cases) if cases else 0,
        "distraction_delta": None,
        "failures": failures,
    }


def _run_agent(command: list[str], payload: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    env = os.environ.copy()
    env["JANITOR_EVAL_MODE"] = str(payload["mode"])
    env["JANITOR_EVAL_PROVIDER"] = str(payload["provider"])
    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload),
            capture_output=True,
            env=env,
            text=True,
            timeout=timeout_ms / 1000,
        )
    except subprocess.TimeoutExpired as error:
        return {"success": False, "error": f"agent timed out after {timeout_ms} ms", "stdout": error.stdout or "", "stderr": error.stderr or ""}

    parsed = _parse_json(result.stdout)
    if isinstance(parsed, dict) and isinstance(parsed.get("success"), bool):
        return {
            "success": parsed["success"] and result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": parsed.get("error"),
        }
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error": None if result.returncode == 0 else f"agent exited with {result.returncode}",
    }


def _read_cases(path: str) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        cases: Any = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        payload = _read_json(path)
        cases = payload.get("cases", payload.get("evals")) if isinstance(payload, dict) else payload

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


def _print_table(rows: list[dict[str, Any]]) -> None:
    headers = ["Mode", "Provider", "Cases", "Successes", "Success rate", "Distraction Delta", "Failures"]
    keys = ["mode", "provider", "cases", "successes", "success_rate", "distraction_delta", "failures"]
    display_rows = []
    for row in rows:
        display_rows.append(
            {
                **row,
                "success_rate": f"{row['success_rate']:.1%}",
                "distraction_delta": _format_delta(row["distraction_delta"]),
                "failures": _failure_summary(row["failures"]),
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


def _format_delta(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1%}"


def _threshold_failures(
    rows: list[dict[str, Any]],
    min_success_rate: float | None,
    min_distraction_delta: float | None,
) -> list[str]:
    failures = []
    for row in rows:
        if row["mode"] != "janitor":
            continue
        provider = row["provider"]
        success_rate = row["success_rate"]
        if min_success_rate is not None and success_rate < min_success_rate:
            failures.append(
                f"{provider} agent success {success_rate:.1%} is below minimum {min_success_rate:.1%}"
            )
        delta = row["distraction_delta"]
        if min_distraction_delta is not None and delta is not None and delta < min_distraction_delta:
            failures.append(
                f"{provider} Distraction Delta {delta:.1%} is below minimum {min_distraction_delta:.1%}"
            )
    return failures


def _failure_summary(failures: list[dict[str, Any]]) -> str:
    if not failures:
        return "-"
    return "; ".join(str(failure.get("id") or failure["prompt"]) for failure in failures[:3])


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
