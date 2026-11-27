# 010 — Docker: multi-stage python:3.13-slim image, non-root, Compose with a named volume

- Status: accepted
- Date: 2026-11-27

## Context

The service must run identically on the laptop (WSL2 + Docker Desktop), in CI and on a small Ubuntu VPS with Docker Compose. The image should contain no build tools or dev dependencies, run without root, report its health to Docker, and keep the SQLite database across container rebuilds. `/metrics` and the API are unauthenticated (decision 009).

## Options considered

Measured on 2026-11-27:

| Base image | Size | Python | Shell | libc |
|---|---|---|---|---|
| **python:3.13-slim** | 176 MB | 3.13.18 (same as dev) | yes | glibc 2.41 |
| python:3.13-alpine | 70 MB | 3.13.18 | yes | musl |
| distroless/python3-debian13 | 91 MB | 3.13.5 (Debian build, not selectable) | no | glibc 2.41 |
| distroless/python3-debian12 | 80 MB | 3.11.2 (too old for `requires-python >= 3.13`) | no | glibc 2.36 |

- **Alpine:** musl instead of glibc. Some packages need compiling, and musl's DNS resolver behaves differently, which matters because the SSRF check relies on `getaddrinfo`.
- **Distroless:** smallest attack surface. But its Python version can't be chosen, a venv built on `python:3.13-slim` (`/usr/local/bin/python`) does not work with its `/usr/bin/python3`, and there is no shell for debugging.

## Decision

- **Base image:** `python:3.13-slim` for both stages.
- **Builder stage:**
  - copies the uv binary from `ghcr.io/astral-sh/uv:0.13.9`, the same version as development;
  - copies `pyproject.toml` and `uv.lock` first (layer caching), then runs `uv sync --locked --no-dev --compile-bytecode --no-python-downloads --link-mode copy`.
- **Runtime stage:**
  - only `/app/.venv` and `site_monitor/`: no uv, pytest, ruff, tests or docs (verified inside the image);
  - a system user `app` (uid 10001);
  - `/data` is created and owned by `app` in the image, because a new named volume copies the ownership of its mount point;
  - `PYTHONUNBUFFERED=1`, so logs appear immediately;
  - `HEALTHCHECK` written in Python with `urllib` (slim has no curl);
  - exec-form `CMD` so uvicorn is PID 1 and receives `SIGTERM` directly.
- **`.dockerignore`:** keeps `.git`, `.venv`, `.env`, databases, caches, tests and docs out of the build context.
- **`docker-compose.yml`:**
  - port `127.0.0.1:8000:8000`, so the service is not reachable from other machines;
  - settings from `.env` with defaults; named volume `site-monitor-data` at `/data`; `restart: unless-stopped`;
  - hardening: `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges`.
- Makefile targets `docker-build`, `up`, `down`.

## Consequences

Verified results:

- The image is 204 MB.
- The container becomes `healthy` within seconds.
- The SSRF check blocks `169.254.169.254` inside the container too.
- Writes outside `/data` fail (read-only root filesystem).
- `docker compose stop` completes in about 0.6 s with exit code 0, and the lifespan shutdown runs.
- Targets survive `docker compose down` + `up`.

Other consequences:

- `docker compose down -v` deletes the volume, and with it the database. Backups must use SQLite's online backup (decision 004), not a plain file copy of a running database.
- `python:3.13-slim` is a moving tag: rebuilding picks up Debian and Python patch updates, which is good for security but not bit-for-bit reproducible. Pinning by digest (`python:3.13-slim@sha256:...`) with automated update PRs would make builds reproducible.
- The Dockerfile is not linted yet (hadolint is not installed).
- Prometheus will reach `/metrics` through the internal Docker network, not through the published port.
- Only one container may run (decision 007).

## I would choose differently if...

- the organisation required minimal images and had tooling for debugging shell-less containers: distroless, with a builder that matches its Python;
- the app were a static binary (Go/Rust) or had no compiled dependencies and no DNS-sensitive logic: Alpine would be a reasonable size win.
