# 003 — ruff for linting and formatting, Makefile for common commands

- Status: accepted
- Date: 2026-11-25

## Context

The project needs an automatic check for likely bugs (lint) and a single code style (format), runnable both locally and in CI. Developers and CI should run the same commands.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **ruff** | One tool for lint and format; very fast; reimplements flake8, isort, pyupgrade, bugbear rules; configured in `pyproject.toml` | Younger tool; a few niche plugins missing |
| flake8 + black (+ isort) | Long-established | 3 tools, 3 configs, 3 versions to keep in sync; slower |
| pylint | Very thorough analysis | Slow and noisy, needs tuning; not a formatter |

## Decision

- `ruff` 0.17 as a dev dependency, for both `ruff check` (lint) and `ruff format` (format).
- **No `[tool.ruff]` configuration.** The ruff 0.17 default rule set is already broad (pyflakes, bugbear, pyupgrade, import sorting, async and some security rules), and `target-version` is taken from `requires-python`. Rules will be added or ignored only when there is a concrete reason.
- A `Makefile` with `install`, `lint`, `format`, `test`, `run`. `make lint` only checks and never modifies files (for CI); `make format` rewrites files (for local use).

## Consequences

- CI (step 11) will call `make lint` and `make test`, the same commands as on the laptop.
- The ruff version is pinned by `uv.lock`, so a new ruff release with new default rules cannot break CI until the lock is upgraded on purpose.
- ruff's formatter also reads Markdown files (to format Python code blocks inside them); this is the default and harmless here.
- Not included: a type checker (mypy/pyright) and git pre-commit hooks. They can be added later as separate decisions.

## I would choose differently if...

- an existing codebase already had a tuned flake8 + black setup and migrating would only create noise in the history;
- the team wanted deep design-level analysis and accepted the tuning cost (pylint, alongside a formatter).
