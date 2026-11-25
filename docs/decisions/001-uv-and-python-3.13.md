# 001 — Use uv for dependencies and pin Python 3.13

- Status: accepted
- Date: 2026-11-25

## Context

The project needs a reproducible Python environment: the same interpreter and the same dependency versions on the laptop (WSL2), in CI (GitHub Actions) and in the Docker image. The system Python on the dev machine is 3.10, which reached end of life in October 2026.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| pip + venv + `requirements.txt` | Built into Python, universally known | No real lockfile without extra tools (pip-tools); manual venv handling; slow |
| **uv** | Fast; one tool for venv, dependencies, lockfile and Python versions; standard `pyproject.toml`; official Docker and GitHub Actions support | Younger tool (2024), one more thing to learn |
| Poetry | Mature, has a lockfile | Slower; historically non-standard config; losing ground to uv for new projects |

Python version: 3.12 (already present, security fixes only), **3.13** (mature, supported until 2029), 3.14/3.15 (newest, less proven library support).

## Decision

Use **uv**, with Python **3.13** pinned in `.python-version` and `requires-python = ">=3.13"` in `pyproject.toml`. `uv.lock` is committed. The virtual environment lives in `.venv/` inside the project and is not committed.

## Consequences

- `uv sync` recreates the exact environment from `uv.lock`. The same command will be used in CI and in the Dockerfile.
- uv downloads Python 3.13 into the user's home directory (`~/.local/share/uv/python`), so the system Python is untouched.
- Contributors need uv installed. The project still uses standard `pyproject.toml`, so moving back to pip later is possible.

## I would choose differently if...

- the team or company already standardised on pip/Poetry, since consistency beats a small speed gain;
- the target platform only allowed the distribution's Python packages (some locked-down servers), in which case it would be pip + venv on the system Python.
