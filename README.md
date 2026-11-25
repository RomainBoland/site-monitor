# site-monitor

A small service that checks whether websites are up and exposes the results as Prometheus metrics.

> Work in progress. Progress is tracked in [docs/roadmap.md](docs/roadmap.md), and every technical choice is explained in [docs/decisions/](docs/decisions/).

## Requirements

- [uv](https://docs.astral.sh/uv/). It installs the pinned Python version (3.13) and the dependencies.

## Getting started

```bash
uv sync          # create .venv and install the exact versions from uv.lock
cp .env.example .env
```

Common commands (see the [Makefile](Makefile)):

```bash
make lint      # ruff lint + format check (same as CI)
make format    # auto-fix and format the code
make test      # run the tests
make run       # start the API on http://127.0.0.1:8000 (docs at /docs)
```

## Architecture

_To be written (step 12)._
