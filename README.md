# Context Janitor

Context Janitor is a small CLI middleware for pruning oversized LLM tool catalogs.
Give it a user prompt and a `tools` JSON file, and it returns only the most relevant tools.

It is meant for agent stacks where sending every available tool is expensive and noisy.
The default ranker is deterministic and dependency-free. Optional provider modes can ask a
fast model to make the selection.

## Install

```powershell
pip install -e .
```

## Quick Start

```powershell
janitor prune --prompt "Search GitHub issues and make a PR" --tools examples/tools.json --limit 2
```

Output:

```json
{
  "selected": [
    {
      "name": "github_search_issues",
      "description": "Search issues in a GitHub repository."
    },
    {
      "name": "github_create_pr",
      "description": "Open a pull request with a title, body, and branch."
    }
  ],
  "metadata": {
    "provider": "heuristic",
    "limit": 2,
    "available_tools": 8
  }
}
```

## Tool Formats

Context Janitor accepts plain tool objects:

```json
[
  { "name": "github_create_pr", "description": "Open a pull request." }
]
```

It also accepts OpenAI-style tool definitions:

```json
[
  {
    "type": "function",
    "function": {
      "name": "github_create_pr",
      "description": "Open a pull request."
    }
  }
]
```

## Provider Modes

The default provider is `heuristic`, which requires no network or API key.

```powershell
janitor prune --provider heuristic --prompt "summarize this PDF" --tools tools.json
```

You can also use a model provider:

```powershell
$env:OPENAI_API_KEY = "..."
janitor prune --provider openai --model "your-fast-model" --prompt "summarize this PDF" --tools tools.json
```

Supported provider values are:

- `heuristic`
- `openai`
- `anthropic`
- `gemini`

Provider calls use only the Python standard library. If a provider is unavailable, the CLI exits
with a clear error instead of silently choosing tools.

## Middleware Mode

To prune an OpenAI-compatible request payload, pass JSON on stdin:

```powershell
Get-Content request.json | janitor middleware --limit 5
```

The command reads `messages` and `tools`, prunes the tool list, and writes the modified request JSON.

## Why This Exists

Agents become less reliable when tool lists grow large and overlapping. Context Janitor keeps the
tool surface small, which usually means fewer prompt tokens, fewer wrong tool calls, and easier
debugging when an agent takes an unexpected turn.
