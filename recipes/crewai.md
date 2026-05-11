# CrewAI

CrewAI agents often accumulate broad tool lists. Keep the agent definition stable, but prune the
tools immediately before kickoff.

```python
import json
import subprocess


def prune_for_task(task_description: str, crewai_tools: list, raw_tool_catalog: list[dict]):
    request = {
        "messages": [{"role": "user", "content": task_description}],
        "tools": raw_tool_catalog,
    }
    result = subprocess.run(
        ["janitor", "middleware"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
    )
    selected_names = {
        tool.get("function", tool).get("name")
        for tool in json.loads(result.stdout)["tools"]
    }
    return [tool for tool in crewai_tools if tool.name in selected_names]


researcher.tools = prune_for_task(task.description, researcher.tools, raw_tool_catalog)
crew.kickoff()
```

Use `.janitor.yaml` at the project root to set provider, model, timeout, fallback, and caching once.
