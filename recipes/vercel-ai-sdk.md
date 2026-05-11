# Vercel AI SDK

The CLI can sit in front of any OpenAI-compatible request payload. In a Node app, call it before
`streamText`.

```ts
import { spawnSync } from "node:child_process";
import { openai } from "@ai-sdk/openai";
import { streamText } from "ai";

function pruneTools(prompt: string, tools: Record<string, unknown>) {
  const request = {
    messages: [{ role: "user", content: prompt }],
    tools: Object.values(tools),
  };

  const result = spawnSync("janitor", ["middleware"], {
    input: JSON.stringify(request),
    encoding: "utf8",
  });

  if (result.status !== 0) {
    throw new Error(result.stderr);
  }

  return JSON.parse(result.stdout).tools;
}

const prompt = "Search the docs and open an issue";
const selectedTools = pruneTools(prompt, tools);

const result = streamText({
  model: openai("gpt-4o-mini"),
  prompt,
  tools: selectedTools,
});
```

For serverless paths, keep `provider: heuristic` or enable `cache: true` to avoid adding network
latency before the main model call.
