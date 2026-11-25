# 002 — FastAPI as web framework, pytest as test runner

- Status: accepted
- Date: 2026-11-25

## Context

The service is a small JSON API (target CRUD, `/health`, `/metrics`) that must validate user input (URLs, SSRF checks) and will run periodic HTTP checks in the background. It runs on a small VPS (2–4 GB RAM) and must be explainable in a junior DevOps interview.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **FastAPI** | Validation from type hints (Pydantic); automatic OpenAPI docs at `/docs`; native async; most common choice for new Python APIs | More dependencies; needs an ASGI server (uvicorn); async takes some learning |
| Flask | Simple, very widespread | Validation must be written by hand or added; mainly synchronous |
| Django | Everything included (ORM, admin, auth) | Too heavy for a ~6-endpoint API; more RAM, more conventions |

Test runner: **pytest** (plain `assert`, fixtures, the de facto standard) vs `unittest` (standard library, more boilerplate).

## Decision

- Runtime dependencies: `fastapi`, `uvicorn` (the ASGI server that runs the app).
- Dev dependencies: `pytest`, `httpx2` (required by FastAPI's `TestClient`).
- Code lives in the `site_monitor/` package; tests live in `tests/`.

**httpx vs httpx2:** the plan was `httpx`, but the installed Starlette 1.10.0 (which FastAPI is built on) marks `httpx` as deprecated for `TestClient` and asks for `httpx2` (maintained by the Pydantic organization, github.com/pydantic/httpx2). The name was checked against the Starlette source and PyPI before installing, because a name this close to a popular package is a common typosquatting pattern.

## Consequences

- Request/response validation for later steps comes from Pydantic models, not hand-written checks.
- The app is started with `uv run uvicorn site_monitor.main:app`.
- `pytest` and `httpx2` are dev-only, so they will not be installed in the production image.
- `/health` is a liveness check only: it does not touch the database or the monitored sites, so one slow site cannot make the container "unhealthy".

## I would choose differently if...

- the project needed server-rendered HTML pages, users and an admin interface (Django);
- the team already ran Flask services and shared tooling for them (Flask).
