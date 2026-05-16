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
- Render or update `assets/heuristic-flow.svg` if the heuristic flow changes
- Remove stale `dist/` and `build/` artifacts before building a publishable package
- Upload only the artifacts for the current version, not every file in `dist/`
- Create a matching Git tag, such as `v1.0.0rc3`
- For Trusted Publishing, configure PyPI to trust `.github/workflows/publish.yml` with the
  `pypi` GitHub environment, then publish from a GitHub Release.
