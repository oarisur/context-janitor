# Production Rollout

Use this checklist when moving Context Janitor from pilot traffic to production traffic.

## 1. Build A Real Eval Pack

Start from agent logs, not synthetic prompts. Aim for 50-100 representative cases before relying on
the results.

Create a first draft from JSON or JSONL logs:

```powershell
python scripts\prepare_evals.py `
  --logs agent-logs.jsonl `
  --success-field success `
  --output production-evals.draft.json
```

The default log fields are:

- `prompt`
- `tool_calls`
- `id`

Use `--prompt-field`, `--tool-field`, and `--id-field` for nested log shapes such as
`input.prompt` or `trace.id`.

Each case should include:

- `id`: stable identifier for triage
- `prompt`: the user or agent task prompt
- `expected_tool` or `expected_tools`: tools that must survive pruning
- optional notes in your own tracking system for expected outcome and grading rationale

Example:

```json
{
  "id": "support-billing-issue-search",
  "prompt": "Find open GitHub issues related to billing support escalation.",
  "expected_tool": "github_search_issues"
}
```

Review the draft before using it as a gate. The extractor records `source_index` on each case so
you can trace it back to the original log row.

## 2. Gate Tool Selection

Run the real prompt eval with a threshold:

```powershell
python scripts\evaluate.py `
  --tools production-tools.json `
  --evals production-evals.json `
  --providers heuristic `
  --limit 5 `
  --min-accuracy 0.95
```

Start with `heuristic`; add API providers only when you need a router model and have timeout,
fallback, and cost expectations documented.

## 3. Gate Agent Success

Wrap your real agent in a command that reads the eval payload from stdin and prints:

```json
{ "success": true }
```

Then compare the full catalog against Janitor-pruned catalogs:

```powershell
python scripts\eval_agent.py `
  --tools production-tools.json `
  --evals production-evals.json `
  --providers heuristic `
  --limit 5 `
  --min-janitor-success-rate 0.90 `
  --min-distraction-delta 0.00 `
  -- python run_agent_eval.py
```

For early production, require `Distraction Delta >= 0`. That means Janitor must not reduce task
success versus the full catalog. Raise the threshold only after you have enough cases to trust the
measurement.

## 4. Lint The Catalog

Run catalog lint before shipping tool description changes:

```powershell
janitor lint --tools production-tools.json
```

Fix duplicate names, empty descriptions, overly vague tool names, repeated descriptions, malformed
schemas, and very long descriptions. Good names and descriptions are part of the ranking surface.

If results look stale while you are editing tool descriptions, inspect or clear the cache:

```powershell
janitor cache-info
janitor clear-cache
```

## 5. Roll Out Gradually

Recommended rollout:

- dry run in logs only
- small internal traffic slice
- limited production slice with fallback enabled
- broader production traffic after evals and logs agree

Keep `fallback: heuristic` for API-backed providers unless your application requires hard failure.

## 6. Track Release Metrics

For every release, record:

- selection accuracy
- baseline agent success
- Janitor agent success
- Distraction Delta
- payload compression
- provider fallback count
- p95 middleware latency
