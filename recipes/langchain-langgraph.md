# LangChain / LangGraph

Use Context Janitor before binding tools to your model. The important bit is that the model only
sees the pruned list.

```python
import json
import subprocess

from langchain_openai import ChatOpenAI


def prune_tools(prompt: str, tools: list[dict], limit: int = 5) -> list[dict]:
    request = {
        "messages": [{"role": "user", "content": prompt}],
        "tools": tools,
    }
    result = subprocess.run(
        ["janitor", "middleware", "--limit", str(limit)],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)["tools"]


prompt = "Find GitHub issues about auth and open a PR"
selected_tools = prune_tools(prompt, all_tools)

llm = ChatOpenAI(model="gpt-4o-mini")
agent_ready_llm = llm.bind_tools(selected_tools)
```

For LangGraph, run the same pruning step in the node that prepares the model call, then pass the
trimmed tool list into the model node state.
