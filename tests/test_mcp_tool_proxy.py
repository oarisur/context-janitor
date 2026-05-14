import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

from context_janitor.mcp_proxy import prune_tools_list_response


ROOT = Path(__file__).resolve().parents[1]
PROXY_PATH = ROOT / "scripts" / "mcp_tool_proxy.py"


def _load_proxy():
    spec = importlib.util.spec_from_file_location("mcp_tool_proxy", PROXY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class McpToolProxyTest(unittest.TestCase):
    def test_proxy_help_runs_from_checkout(self):
        result = subprocess.run(
            [sys.executable, "scripts/mcp_tool_proxy.py", "--help"],
            check=True,
            capture_output=True,
            cwd=ROOT,
            text=True,
        )

        self.assertIn("tools/list", result.stdout)

    def test_mcp_proxy_help_runs_from_cli(self):
        result = subprocess.run(
            [sys.executable, "-m", "context_janitor.cli", "mcp-proxy", "--help"],
            check=True,
            capture_output=True,
            cwd=ROOT,
            env=_env(),
            text=True,
        )

        self.assertIn("tools/list", result.stdout)

    def test_mcp_proxy_requires_prompt(self):
        result = subprocess.run(
            [sys.executable, "-m", "context_janitor.cli", "mcp-proxy", "--", sys.executable, "--version"],
            capture_output=True,
            cwd=ROOT,
            env=_env(),
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--prompt or JANITOR_PROMPT is required", result.stderr)

    def test_prune_tools_list_response_keeps_relevant_tools(self):
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "github_search_issues",
                        "description": "Search GitHub issues by text.",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "pdf_extract_text",
                        "description": "Extract text from PDF files.",
                        "inputSchema": {"type": "object"},
                    },
                ]
            },
        }

        pruned = prune_tools_list_response(message, "Find GitHub issues", limit=1)

        self.assertEqual(pruned["result"]["tools"][0]["name"], "github_search_issues")
        self.assertEqual(pruned["result"]["tools"][0]["inputSchema"], {"type": "object"})
        self.assertEqual(pruned["result"]["_janitor"]["original_tools"], 2)
        self.assertEqual(pruned["result"]["_janitor"]["selected_tools"], 1)

    def test_prune_tools_list_response_ignores_non_tool_messages(self):
        message = {"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}}

        self.assertEqual(prune_tools_list_response(message, "anything", limit=1), message)

    def test_script_reexports_package_proxy_function(self):
        proxy = _load_proxy()

        self.assertIs(proxy.prune_tools_list_response, prune_tools_list_response)


def _env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(ROOT / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return env


if __name__ == "__main__":
    unittest.main()
