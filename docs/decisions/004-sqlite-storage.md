# 004 — SQLite via the standard library for storage

- Status: accepted
- Date: 2026-11-25

## Context

The service must remember the list of monitored URLs across restarts and container rebuilds, and later each target's state (up/down, consecutive failures). The data is small (tens of rows), there is a single app process, and it runs on a small VPS (2–4 GB RAM).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **SQLite via `sqlite3` (standard library)** | No dependency; one file on a Docker volume; no extra container; plain, readable SQL | No migration tool; one writer at a time; manual row mapping |
| SQLAlchemy (+ Alembic) | Industry-standard ORM; easy switch to Postgres; versioned migrations | Large abstraction for one table; harder to debug and to defend |
| PostgreSQL container | Production standard; concurrent writers; replication, mature backups | Another service to run, secure, back up and monitor; ~100+ MB RAM; overkill for a URL list |

## Decision

Use SQLite through Python's built-in `sqlite3` module, with plain SQL in `site_monitor/db.py`.

- The database file path comes from the `DATABASE_PATH` environment variable (default `site-monitor.db`), documented in `.env.example`.
- The schema is created with `CREATE TABLE IF NOT EXISTS` (`init_db`), so it is safe to run at every startup.
- Every query uses `?` placeholders, never string formatting, to prevent SQL injection.
- `url` has a `UNIQUE` constraint, so the database itself rejects duplicates.
- Functions receive a connection as a parameter; tests use a temporary database file per test.

## Consequences

- Zero new dependencies; nothing extra to run on the VPS.
- In Docker (step 10) the database file must live on a volume, or it is lost when the container is recreated.
- Backups are a file copy, but it must be done safely while the app runs (for example `sqlite3 site-monitor.db ".backup backup.db"`), not a plain `cp` in the middle of a write.
- No versioned migrations: schema changes (e.g. the state columns in step 8) will be handled by hand. If the schema keeps evolving, adding a migration tool is the first improvement.
- One writer at a time: fine for one API process plus one checker. When the checker writes in parallel with the API (steps 7–8), WAL mode may be needed; that will be decided then.

## I would choose differently if...

- the app needed several instances behind a load balancer, or many concurrent writers (PostgreSQL);
- the data model grew to many related tables or needed frequent schema changes (SQLAlchemy + Alembic, on SQLite or Postgres).
