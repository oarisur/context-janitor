from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a draft eval pack from agent logs.")
    parser.add_argument("--logs", required=True, help="Path to JSON or JSONL agent logs.")
    parser.add_argument("--output", help="Write eval pack JSON to this path. Defaults to stdout.")
    parser.add_argument("--prompt-field", default="prompt", help="Dot path for the prompt field.")
    parser.add_argument("--tool-field", default="tool_calls", help="Dot path for tool call names.")
    parser.add_argument("--id-field", default="id", help="Dot path for a stable case id.")
    parser.add_argument(
        "--success-field",
        help="Optional dot path for a boolean success field. When set, failed rows are skipped by default.",
    )
    parser.add_argument(
        "--include-failures",
        action="store_true",
        help="Include failed rows even when --success-field is provided.",
    )
    parser.add_argument(
        "--include-unlabeled",
        action="store_true",
        help="Include rows without tool labels as needs_review cases.",
    )
    args = parser.parse_args()

    logs = _read_records(args.logs)
    cases, skipped = _prepare_cases(
        logs,
        prompt_field=args.prompt_field,
        tool_field=args.tool_field,
        id_field=args.id_field,
        success_field=args.success_field,
        include_failures=args.include_failures,
        include_unlabeled=args.include_unlabeled,
    )
    payload = {
        "metadata": {
            "source": args.logs,
            "records": len(logs),
            "cases": len(cases),
            "skipped": skipped,
            "review_required": any(case.get("needs_review") for case in cases),
        },
        "cases": cases,
    }

    text = json.dumps(payload, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")
    return 0


def _prepare_cases(
    records: list[dict[str, Any]],
    prompt_field: str,
    tool_field: str,
    id_field: str,
    success_field: str | None,
    include_failures: bool,
    include_unlabeled: bool,
) -> tuple[list[dict[str, Any]], int]:
    cases: list[dict[str, Any]] = []
    skipped = 0
    for index, record in enumerate(records, start=1):
        if success_field and not include_failures and _get_path(record, success_field) is False:
            skipped += 1
            continue

        prompt = _get_path(record, prompt_field)
        if not isinstance(prompt, str) or not prompt.strip():
            skipped += 1
            continue

        expected_tools = _tool_names(_get_path(record, tool_field))
        if not expected_tools and not include_unlabeled:
            skipped += 1
            continue

        case_id = _get_path(record, id_field)
        case: dict[str, Any] = {
            "id": str(case_id) if case_id is not None else f"log-{index:04d}",
            "prompt": prompt.strip(),
            "expected_tools": expected_tools,
            "source_index": index - 1,
        }
        if not expected_tools:
            case["needs_review"] = True
        cases.append(case)
    return cases, skipped


def _read_records(path: str) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        payload: Any = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("records", payload.get("logs", payload.get("items")))

    if not isinstance(payload, list):
        raise ValueError("Log file must contain a list, or an object with records/logs/items.")
    records = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Log record at index {index} must be an object.")
        records.append(item)
    return records


def _get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _tool_names(value: Any) -> list[str]:
    names: list[str] = []
    _collect_tool_names(value, names)
    return list(dict.fromkeys(name for name in names if name))


def _collect_tool_names(value: Any, names: list[str]) -> None:
    if isinstance(value, str):
        names.append(value)
    elif isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str):
            names.append(name)
        function = value.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            names.append(function["name"])
        tool_name = value.get("tool_name")
        if isinstance(tool_name, str):
            names.append(tool_name)
    elif isinstance(value, list):
        for item in value:
            _collect_tool_names(item, names)


if __name__ == "__main__":
    raise SystemExit(main())
