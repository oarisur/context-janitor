from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_simulated_data.py"

spec = importlib.util.spec_from_file_location("generate_simulated_data", MODULE_PATH)
assert spec is not None
assert spec.loader is not None
generate_simulated_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate_simulated_data)


def test_generate_dataset_creates_realistic_pack() -> None:
    tools, cases, logs = generate_simulated_data.generate_dataset()

    assert len(tools) == 100
    assert len(cases) == 100
    assert len(logs) == 100
    assert cases[0]["expected_tools"] == ["github_search_issues"]
    assert logs[0]["tool_calls"][0]["function"]["name"] == "github_search_issues"


def test_write_dataset_outputs_expected_files(tmp_path: Path) -> None:
    tools, cases, logs = generate_simulated_data.generate_dataset(cases_per_tool=1)

    generate_simulated_data.write_dataset(tmp_path, tools, cases, logs)

    tools_payload = json.loads((tmp_path / "simulated_production_tools.json").read_text())
    eval_payload = json.loads((tmp_path / "simulated_production_evals.json").read_text())
    log_lines = (tmp_path / "simulated_agent_logs.jsonl").read_text().splitlines()

    assert len(tools_payload) == 100
    assert eval_payload["metadata"]["cases"] == 20
    assert len(log_lines) == 20
