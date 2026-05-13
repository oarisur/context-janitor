from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full Context Janitor release gate.")
    parser.add_argument(
        "--skip-wheel-smoke",
        action="store_true",
        help="Skip installing the built wheel in a temporary virtual environment.",
    )
    args = parser.parse_args()

    checks = [
        ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
        ("mypy", [sys.executable, "-m", "mypy", "src", "scripts"]),
        ("pytest", [sys.executable, "-m", "pytest"]),
        (
            "catalog lint",
            [
                sys.executable,
                "-m",
                "context_janitor.cli",
                "lint",
                "--tools",
                "examples/tools.json",
            ],
        ),
        (
            "prepare evals",
            [
                sys.executable,
                "scripts/prepare_evals.py",
                "--logs",
                "examples/agent_logs.example.jsonl",
                "--success-field",
                "success",
            ],
        ),
        (
            "selection eval",
            [
                sys.executable,
                "scripts/evaluate.py",
                "--tools",
                "examples/tools.json",
                "--evals",
                "examples/evals.example.json",
                "--providers",
                "heuristic",
                "--limit",
                "2",
                "--min-accuracy",
                "1.0",
            ],
        ),
        (
            "agent eval",
            [
                sys.executable,
                "scripts/eval_agent.py",
                "--tools",
                "examples/tools.json",
                "--evals",
                "examples/evals.example.json",
                "--providers",
                "heuristic",
                "--limit",
                "2",
                "--min-janitor-success-rate",
                "1.0",
                "--min-distraction-delta",
                "0.0",
                "--",
                sys.executable,
                "examples/agent_runner_mock.py",
            ],
        ),
        ("build", [sys.executable, "-m", "build"]),
    ]

    for name, command in checks:
        if _run(name, command) != 0:
            return 1

    try:
        _inspect_sdist()
    except RuntimeError as error:
        print(f"\n[release-check] FAIL sdist inspection: {error}", file=sys.stderr)
        return 1
    print("[release-check] PASS sdist inspection")

    if not args.skip_wheel_smoke:
        try:
            _wheel_smoke()
        except RuntimeError as error:
            print(f"\n[release-check] FAIL wheel smoke: {error}", file=sys.stderr)
            return 1
        print("[release-check] PASS wheel smoke")

    print("\n[release-check] PASS all release checks")
    return 0


def _run(name: str, command: list[str]) -> int:
    print(f"\n[release-check] RUN {name}")
    print(f"[release-check] $ {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        print(f"[release-check] FAIL {name} exited with {result.returncode}", file=sys.stderr)
    else:
        print(f"[release-check] PASS {name}")
    return result.returncode


def _inspect_sdist() -> None:
    sdist = ROOT / "dist" / "context_janitor-0.1.0.tar.gz"
    if not sdist.exists():
        raise RuntimeError(f"missing expected sdist: {sdist}")

    with tarfile.open(sdist) as archive:
        names = archive.getnames()

    required = {
        "context_janitor-0.1.0/docs/production-rollout.md",
        "context_janitor-0.1.0/examples/agent_logs.example.jsonl",
        "context_janitor-0.1.0/scripts/eval_agent.py",
        "context_janitor-0.1.0/scripts/prepare_evals.py",
        "context_janitor-0.1.0/src/context_janitor/py.typed",
    }
    missing = sorted(required - set(names))
    if missing:
        raise RuntimeError(f"sdist missing required files: {missing}")
    if any(name.endswith((".pyc", ".pyo")) for name in names):
        raise RuntimeError("sdist contains Python bytecode")


def _wheel_smoke() -> None:
    wheel = _latest_wheel()
    with tempfile.TemporaryDirectory() as temp_dir:
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(temp_dir)
        python = _venv_python(Path(temp_dir))

        _run_checked("install wheel", [str(python), "-m", "pip", "install", str(wheel)])
        _run_checked(
            "wheel prune",
            [
                str(python),
                "-m",
                "context_janitor.cli",
                "prune",
                "--prompt",
                "Search GitHub issues",
                "--tools",
                str(ROOT / "examples" / "tools.json"),
                "--limit",
                "2",
                "--format",
                "names",
            ],
        )
        _run_checked(
            "wheel lint",
            [
                str(python),
                "-m",
                "context_janitor.cli",
                "lint",
                "--tools",
                str(ROOT / "examples" / "tools.json"),
            ],
        )


def _latest_wheel() -> Path:
    wheels = sorted((ROOT / "dist").glob("context_janitor-*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise RuntimeError("no built wheel found in dist")
    return wheels[-1]


def _venv_python(path: Path) -> Path:
    if sys.platform == "win32":
        return path / "Scripts" / "python.exe"
    return path / "bin" / "python"


def _run_checked(name: str, command: list[str]) -> None:
    print(f"[release-check] $ {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise RuntimeError(f"{name} exited with {result.returncode}")


if __name__ == "__main__":
    raise SystemExit(main())
