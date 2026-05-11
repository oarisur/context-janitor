# Context Janitor

**97.0% tool-selection accuracy at 0ms median latency, with zero router cost.**

![Context Janitor terminal demo](assets/terminal-demo.svg)

Context Janitor is a CLI and Python library for pruning oversized LLM tool catalogs.
Give it a user prompt and a `tools` JSON file, and it returns only the tools the agent is likely
to need.

It is built for agent stacks where sending every available tool is expensive, slow, and noisy.
If an API router fails, Context Janitor falls back to a local heuristic so your pipeline keeps
moving.

It is MCP-compatible by design: MCP servers expose structured tool definitions, and Context
Janitor can sit between those JSON tool catalogs and your agent runtime.

## Benchmark Snapshot

```text
+-----------------------+--------------------+---------------+-----------+--------+-----------------+------------------+-------------+
| Mode                  | Selection accuracy | Agent success | Median ms | p95 ms | Router cost/run | Tool payload/run | Compression |
+-----------------------+--------------------+---------------+-----------+--------+-----------------+------------------+-------------+
| No Janitor (baseline) | 100.0%             | not measured  | 0         | 0      | $0.000000       | $0.001060        | 0.0%        |
| heuristic             | 97.0%              | not measured  | 0         | 0      | $0.000000       | $0.000328        | 69.1%       |
+-----------------------+--------------------+---------------+-----------+--------+-----------------+------------------+-------------+
```

`Agent success` is intentionally marked `not measured` unless you provide real agent eval data
with `--agent-success-file`.

## Before And After

| Setup | Tools sent | Approx tool tokens | Result |
| --- | ---: | ---: | --- |
| Without Janitor | 50 | 12,000 | Larger payloads, more wrong tool calls |
| With Janitor | 5 | 1,200 | Smaller payloads, clearer tool choice |

Example production log:

```text
[Janitor] INFO event=pruned requested_provider=openai provider=heuristic fallback=true cache_hit=false tools_before=50 tools_after=5 tokens_before=12000 tokens_after=1200 tokens_saved=10800 estimated_savings_usd=0.054000 duration_ms=7
```

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
    "requested_provider": "heuristic",
    "provider": "heuristic",
    "fallback_used": false,
    "cache_hit": false,
    "duration_ms": 1,
    "limit": 2,
    "available_tools": 8,
    "reduced_tokens": 184,
    "estimated_savings_usd": 0.00092
  }
}
```

## Zero-Downtime Fallbacks

Provider mode is fail-open by default:

```powershell
$env:OPENAI_API_KEY = "..."
janitor prune `
  --provider openai `
  --model gpt-4o-mini `
  --prompt "summarize this PDF" `
  --tools tools.json `
  --timeout-ms 800 `
  --fallback heuristic `
  --log-level INFO
```

If OpenAI rate-limits, times out, or is unavailable, Janitor logs a warning and immediately uses
the local heuristic selector.

## .janitor.yaml

Drop this in your project root:

```yaml
provider: anthropic
model: claude-3-haiku-20240307
limit: 5
fallback: heuristic
cache: true
timeout_ms: 800
log_level: INFO
keep: log_error,notify_admin
```

Then run:

```powershell
Get-Content request.json | janitor middleware
```

CLI flags override config values.

## Required Tools

Some production agents have safety, audit, or notification tools that must always remain available.
Use `--keep` to force those tools into the selected set:

```powershell
janitor prune --prompt "Search the web" --tools tools.json --limit 5 --keep log_error,notify_admin
```

Kept tools reserve slots inside the limit, then Janitor fills the remaining slots with the best
ranked matches.

## Middleware Mode

Context Janitor reads OpenAI-compatible request JSON from stdin:

```powershell
Get-Content request.json | janitor middleware --limit 5
```

It reads `messages` and `tools`, prunes the tool list, and writes the modified request JSON to
stdout. Logs go to stderr, so piping stays clean.

## Cache

Enable local prompt caching with:

```powershell
janitor prune --cache --prompt "Summarize the daily logs" --tools tools.json
```

Cache entries live in `~/.janitor_cache/cache.json`. Exact and highly similar prompts reuse the
previous tool selection without calling the provider.

## Tool Formats

Plain tool objects:

```json
[
  { "name": "github_create_pr", "description": "Open a pull request." }
]
```

OpenAI-style tool definitions:

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

Supported provider values:

- `heuristic`
- `openai`
- `anthropic`
- `gemini`

Provider calls use only the Python standard library and default to an 800ms timeout.

## Python API

```python
from context_janitor.models import load_tools
from context_janitor.selection import select_resilient, select_resilient_async

tools = load_tools(tool_json)
result = select_resilient(
    provider="openai",
    model="gpt-4o-mini",
    prompt="Find GitHub issues about auth",
    tools=tools,
    limit=5,
    cache_enabled=True,
    keep=("log_error", "notify_admin"),
)

selected_tools = result.selected
```

## Benchmarks

Run the included 100-prompt benchmark:

```powershell
python scripts/benchmark.py --providers heuristic openai anthropic gemini --openai-model gpt-4o-mini --anthropic-model claude-3-haiku-20240307 --gemini-model gemini-1.5-flash
```

The script prints an Accuracy vs. Time vs. Router Cost table and skips providers without API keys.
Pass measured agent evals with:

```powershell
python scripts/benchmark.py --providers heuristic --agent-success-file examples/agent_success.example.json
```

## Explain And Dry Run

Use `--explain` to see why tools were kept or pruned:

```powershell
janitor prune --prompt "Search GitHub issues" --tools examples/tools.json --limit 2 --explain
```

Use `--dry-run` in middleware mode to preserve the payload and log what Janitor would have changed:

```powershell
Get-Content request.json | janitor middleware --limit 5 --dry-run
```

## Recipes

- [LangChain / LangGraph](recipes/langchain-langgraph.md)
- [CrewAI](recipes/crewai.md)
- [Vercel AI SDK](recipes/vercel-ai-sdk.md)
- [GitHub Actions](recipes/github-actions.md)

## Terminal GIF

The repo includes a VHS tape at [docs/demo.tape](docs/demo.tape). Render it with:

```powershell
vhs docs/demo.tape
```

## Why This Exists

Agents become less reliable when tool lists grow large and overlapping. Context Janitor keeps the
tool surface small, which usually means fewer prompt tokens, fewer wrong tool calls, and easier
debugging when an agent takes an unexpected turn.
