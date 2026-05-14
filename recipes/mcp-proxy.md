# MCP Tool Proxy

Context Janitor can sit in front of an MCP stdio server and prune the `tools/list` response before
it reaches the client.

Important limitation: MCP `tools/list` does not include the user's chat prompt. This proxy is best
for scoped sessions where you already know the task, such as "GitHub issue triage" or "PDF
summarization." Pass that task with `--prompt` or `JANITOR_PROMPT`.

## Run A Downstream Server Through Janitor

```powershell
janitor mcp-proxy `
  --prompt "Find GitHub issues and open pull requests" `
  --limit 5 `
  -- python -m your_mcp_server
```

The proxy forwards all JSON-RPC messages unchanged except responses to `tools/list`. Those responses
are normalized as tool definitions, ranked by Janitor, and returned with fewer tools.

## Claude Desktop Shape

Use the proxy as the MCP server command, then put the real MCP server command after `--`:

```json
{
  "mcpServers": {
    "github-triage-pruned": {
      "command": "python",
      "args": [
        "-m",
        "context_janitor.cli",
        "mcp-proxy",
        "--prompt",
        "Find GitHub issues and open pull requests",
        "--limit",
        "5",
        "--",
        "python",
        "-m",
        "your_mcp_server"
      ]
    }
  }
}
```

Use a narrow prompt per configured server. For broad, general-purpose sessions, keep the normal MCP
server or configure multiple pruned entries by workflow.

## Provider Routing

The proxy defaults to the dependency-free heuristic:

```powershell
janitor mcp-proxy --prompt "Summarize PDFs" --limit 4 -- python -m your_mcp_server
```

You can use an API-backed router with heuristic fallback:

```powershell
$env:OPENAI_API_KEY = "..."
janitor mcp-proxy `
  --provider openai `
  --model gpt-4o-mini `
  --fallback heuristic `
  --prompt "Summarize PDFs" `
  --limit 4 `
  -- python -m your_mcp_server
```
