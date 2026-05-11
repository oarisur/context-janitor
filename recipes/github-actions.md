# GitHub Actions

Copy this workflow into `.github/workflows/context-janitor.yml` to test the CLI in CI.

```yaml
name: Context Janitor

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e .
      - run: python -m unittest discover -s tests
      - run: janitor prune --prompt "Search GitHub issues" --tools examples/tools.json --limit 2
```
