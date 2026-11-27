# ---- Stage 1: build the virtual environment --------------------------------
FROM python:3.13-slim AS builder

# Same uv version as in development, copied from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv

WORKDIR /app

# Copy only the dependency files first: this layer (and the slow install below)
# stays cached as long as the dependencies do not change, even if the code does.
COPY pyproject.toml uv.lock .python-version ./

# --locked: fail if uv.lock does not match pyproject.toml (no silent re-resolve).
# --no-dev: no pytest/ruff in production. --no-python-downloads: use this image's
# Python. --link-mode copy: real files, so the venv can be copied to stage 2.
RUN uv sync --locked --no-dev --compile-bytecode --no-python-downloads --link-mode copy


# ---- Stage 2: runtime image -------------------------------------------------
FROM python:3.13-slim

# Unprivileged user: if the app is compromised, the attacker is not root.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir /data \
    && chown app:app /data
# /data is created here, owned by "app", because a new named volume copies the
# ownership of the directory it is mounted on. Otherwise it would be root-owned.

WORKDIR /app

# Only the venv and the code: no uv, no build cache, no tests.
COPY --from=builder /app/.venv /app/.venv
COPY site_monitor/ ./site_monitor/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/site-monitor.db

USER app

EXPOSE 8000

# No curl in slim images: use Python itself. urlopen raises on errors and on
# non-2xx responses, so the exit code is 1 when the app is unhealthy.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Exec form: uvicorn is PID 1 and receives SIGTERM directly from `docker stop`,
# so the lifespan shutdown (stopping the checker) runs.
# 0.0.0.0 is required inside a container; exposure is restricted in compose.
CMD ["uvicorn", "site_monitor.main:app", "--host", "0.0.0.0", "--port", "8000"]
