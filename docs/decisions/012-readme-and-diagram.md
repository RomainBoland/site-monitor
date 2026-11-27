# 012 — README structure and Mermaid architecture diagram

- Status: accepted
- Date: 2026-11-27

## Context

The README is the entry point for recruiters, interviewers and contributors, who often spend only a couple of minutes on it. It must show what the service does, how it is built, how to run it, and why each choice was made, and it must stay accurate as the code changes.

## Options considered

Architecture diagram format:

| Option | Pros | Cons |
|---|---|---|
| **Mermaid in the README** | Rendered natively by GitHub; plain text, so it is diffable and reviewable in PRs | Limited layout control; does not render in every Markdown viewer |
| Image (PNG/SVG from a drawing tool) | Full visual control | Binary file that goes stale silently; edits need the original tool |
| ASCII art | Renders everywhere | Tedious to maintain; looks dated |

## Decision

- Mermaid `flowchart` for the architecture. Planned components (Prometheus) are drawn with dashed lines, so the diagram never claims something that is not built.
- README sections:
  - overview, architecture, quick start (Docker and development), API;
  - configuration, metrics, security, project layout;
  - **known limitations**;
  - a table linking every decision record.
- Endpoints, settings, defaults and metric names were collected from the code, not from memory. All relative links were checked to exist, and the Docker quick-start commands were run.
- CI status badge at the top, so the latest pipeline result is visible immediately.

## Consequences

- The README has to be updated when endpoints, settings or metrics change. CI does not check this.
- Listing known limitations openly shows that the trade-offs are understood. Each one links to the record that explains it.

## I would choose differently if...

- the documentation grew beyond one page: a docs site (e.g. MkDocs) generated from the `docs/` folder, with the README kept as a short overview.
