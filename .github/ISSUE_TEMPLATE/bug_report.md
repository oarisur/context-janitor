---
name: Bug report
about: Report a Context Janitor CLI, library, provider, or MCP proxy bug
title: ''
labels: bug
assignees: ''

---

**Describe the bug**
A clear description of what went wrong.

**To Reproduce**
Command or code that reproduces the behavior:

```powershell
janitor prune --prompt "..." --tools ...
```

Relevant input shape, if possible:

```json
[]
```

**Expected behavior**
What did you expect Context Janitor to return or do?

**Actual behavior**
What happened instead? Include stderr/stdout when useful.

**Environment**
- Context Janitor version:
- Python version:
- OS:
- Install method: `pip`, editable checkout, other
- Provider: `heuristic`, `openai`, `anthropic`, `gemini`, or MCP proxy

**Tool catalog details**
- Approximate number of tools:
- Tool format: plain JSON, OpenAI tools, MCP tools, other
- Did this involve `--cache`, `.janitor.yaml`, or `--keep`?

**Additional context**
Add any other context, links, or minimal sample files that help explain the problem.
