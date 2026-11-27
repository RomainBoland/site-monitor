# Roadmap

Each step ends with one commit and, when a choice was made, a decision record in [decisions/](decisions/).

- [x] 1. Project skeleton: git init, .gitignore, Python version, dependency/packaging tool, README skeleton — *decision: pip+venv vs uv vs poetry*
- [x] 2. Web framework + `/health` endpoint + first test — *decision: FastAPI vs Flask vs Django; test runner*
- [x] 3. Lint/format + Makefile — *decision: ruff vs flake8+black*
- [x] 4. Storage for targets — *decision: SQLite via stdlib vs SQLAlchemy vs PostgreSQL*
- [x] 5. Targets endpoints (add/list/delete) with input validation
- [x] 6. SSRF protection (refuse localhost/private networks) with dedicated tests; explain why the risk exists
- [x] 7. The checker — *decision: httpx vs requests vs aiohttp; sync vs async; how to schedule periodic checks*
- [x] 8. Consecutive-failure logic and state-change detection
- [x] 9. Prometheus metrics and `/metrics` — *decision: prometheus_client vs OpenTelemetry; which metric types*
- [ ] 10. Dockerfile (multi-stage, non-root, healthcheck) + docker-compose.yml — *decision: slim vs alpine vs distroless base image*
- [ ] 11. CI with GitHub Actions: lint, tests, docker build
- [ ] 12. README with architecture and a table linking all decision records
