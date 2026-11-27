# 011 — CI with GitHub Actions, actions pinned by commit SHA

- Status: accepted
- Date: 2026-11-27

## Context

Every push and pull request must be verified automatically: lint, tests, and a Docker image that actually starts. The repository is on GitHub. A CI pipeline runs third-party code (actions) with access to the repository and its token, so it must be treated as security-sensitive.

## Options considered

How to reference third-party actions:

| Option | Pros | Cons |
|---|---|---|
| Major tag (`@v7`) | Readable; automatic fixes | Tags are movable: a compromised action repo can repoint the tag to malicious code (`tj-actions/changed-files`, March 2025) |
| Exact tag (`@v7.0.1`) | Readable; no surprise upgrades | Still movable or deletable |
| **Full commit SHA + version comment** | Immutable; recommended by GitHub's hardening guide and OpenSSF | Less readable; updates are manual |

## Decision

`.github/workflows/ci.yml`, triggered on push to `main` and on every pull request.

- **Actions pinned by full commit SHA**, looked up via the GitHub API on 2026-11-27, with the version in a comment:

  | Action | Version |
  |---|---|
  | `actions/checkout` | v7.0.1 |
  | `astral-sh/setup-uv` | v10.4.0 |
  | `docker/setup-buildx-action` | v4.4.1 |
  | `docker/build-push-action` | v7.4.0 |

  The inputs used were checked against each action's `action.yml` at that version.
- **Least privilege:** `permissions: contents: read` and `persist-credentials: false` on checkout.
- **`checks` job:**
  - installs uv 0.13.9 (the same as development and the Dockerfile) with its cache;
  - runs `uv sync --locked`, then `make lint` and `make test`, the same commands as locally (decision 003).
- **`docker` job** (`needs: checks`):
  - builds the image with Buildx and the GitHub Actions cache, without pushing (there is no registry yet);
  - **smoke test:** starts the container and waits up to 60 s for Docker to report `healthy`, printing the logs on failure.
- `concurrency` cancels outdated runs on the same branch. Each job has a `timeout-minutes`, so a hung step cannot burn runner minutes indefinitely.

## Consequences

- Verified locally:
  - the `checks` steps pass in a fresh clone (no reliance on local files);
  - the smoke-test script reports `healthy` for the real image, and exits 1 with the startup error for a broken one (`CHECK_CONCURRENCY=0`).
- **Not verified locally:**
  - the workflow syntax: running actionlint was not permitted in the session where this was written;
  - the GitHub-hosted runner itself.
- **Verified on GitHub (2026-11-27):** the first run (commit `c023c51`) succeeded. Both jobs passed, 87 tests ran, the container was healthy on the 4th attempt, and there were no warnings or deprecation notices. This also confirmed the workflow syntax.
- Tests never use the network (fake DNS, `MockTransport`), so CI is not flaky because of external sites.
- Pinned SHAs do not update themselves. Dependabot (or Renovate) for `github-actions` would open update PRs; not set up yet.
- A failing smoke test waits the full 60 s before failing; acceptable for now.

## I would choose differently if...

- the actions were all first-party and internally mirrored: version tags could be acceptable;
- images had to be published: a registry (e.g. GHCR) with `packages: write` granted **only** to a publish job on `main`, plus image signing and SBOMs.
