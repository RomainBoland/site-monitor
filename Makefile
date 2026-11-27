# Developer shortcuts. CI runs the same targets, so local and CI behave the same.
.PHONY: install lint format test run docker-build up down

install:
	uv sync

# Fails without modifying files (used by CI).
lint:
	uv run ruff check
	uv run ruff format --check

# Rewrites files in place (used locally before committing).
format:
	uv run ruff check --fix
	uv run ruff format

test:
	uv run pytest

run:
	uv run uvicorn site_monitor.main:app --reload

docker-build:
	docker compose build

# Start in the background; data is kept in the "site-monitor-data" volume.
up:
	docker compose up -d --build

# Stops and removes the container. The volume (and the database) is kept;
# `docker compose down -v` would delete it.
down:
	docker compose down
