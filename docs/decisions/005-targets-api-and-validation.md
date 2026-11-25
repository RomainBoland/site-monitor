# 005 — Targets API design and input validation

- Status: accepted
- Date: 2026-11-25

## Context

Users register the URLs to monitor through a JSON API (add, list, delete). Input comes from outside, so it must be validated before it is stored and, later, fetched by the checker. No new dependency is needed: FastAPI and Pydantic were approved in decision 002.

## Options considered

URL validation:

| Option | Pros | Cons |
|---|---|---|
| **Pydantic `HttpUrl`** | Already installed; http/https only; rejects malformed and over-long (>2083 chars) URLs; normalizes host case and trailing slash | Accepts `user:password@` and private IPs, so extra checks are needed |
| Plain `str` + hand-written checks (`urllib.parse`) | Full control | Easy to miss edge cases; more code to maintain |

## Decision

- Endpoints and status codes follow REST conventions:
  - `POST /targets` returns `201 Created` with the new target, `409 Conflict` for a duplicate, `422` for invalid input.
  - `GET /targets` returns `200` with the list.
  - `DELETE /targets/{id}` returns `204 No Content`, or `404` if the id does not exist.
- URLs are validated with Pydantic `HttpUrl` and stored in their **normalized** form, so `https://EXAMPLE.com` and `https://example.com/` count as the same target (the `UNIQUE` constraint catches it).
- URLs containing credentials are rejected: they would be stored in plain text and later exposed in `/metrics`.
- Private and local addresses (`127.0.0.1`, `10.x`, …) are **not** blocked yet. This is step 6 (SSRF).
- The table is created once at startup (FastAPI `lifespan`). Each request gets its own SQLite connection through a dependency (`get_conn`) that always closes it.
- `check_same_thread=False` on SQLite connections: FastAPI may open, use and close a connection on different threads of its pool. This is safe because a connection is never shared between requests.

## Consequences

- Invalid input never reaches the database; clients get a precise `422` error explaining what is wrong.
- Stored URLs may differ slightly from what the user typed (trailing slash, lowercase host), and the API returns the normalized form.
- `created_at` comes from SQLite's `CURRENT_TIMESTAMP`, which is UTC without an explicit timezone marker.
- One connection per request is simple and cheap with SQLite (opening a local file); there is no connection pool to tune.

## I would choose differently if...

- the API were public or multi-user: it would need authentication and rate limiting before anything else;
- clients needed to update targets (a `PUT`/`PATCH` endpoint) or paginate a large list.
