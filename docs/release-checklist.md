# Release Checklist

Run the automated release gate before tagging or publishing:

```powershell
python scripts\release_check.py
```

The release gate runs:

- Ruff linting
- mypy type checks
- pytest
- catalog linting
- eval-pack preparation smoke test
- thresholded tool-selection eval
- thresholded messy-prompt eval
- thresholded agent-success eval
- wheel and source distribution build
- source distribution inspection
- installed-wheel CLI smoke test in a temporary virtual environment

Use this shorter command only when you already validated wheel installation separately:

```powershell
python scripts\release_check.py --skip-wheel-smoke
```

Manual release tasks:

- Confirm the version in `pyproject.toml`
- Review `docs/production-rollout.md`
- Replace example eval data with real production eval data for app-specific gates
- Render or update `assets/terminal-demo.svg` if CLI output changed
- Create a matching Git tag, such as `v0.1.0`
