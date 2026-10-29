# Verification evidence

Executed on Linux x86_64, CPython 3.12.14, Node.js 24.19.0.

- `python -m pytest -q --junitxml=reports/tests.xml`: 42 passing checks. One dependency deprecation warning about Starlette's httpx test-client support; no test failure.
- `python -m ruff check backend ml scripts`: passed selected syntax/name correctness checks (E9/F63/F7/F82), not a full style/security audit.
- `python -m compileall -q backend ml scripts`: passed.
- `npm run build`: TypeScript checks and optimized React build passed.
- `npm audit --json`: zero known vulnerabilities after updating Vite to 7.3.7.
- `python -m pip_audit ...`: zero known findings for the locked Python dependency closure. This is a point-in-time advisory check, not proof of security.
- `python ml/synthetic.py` and `python ml/train.py`: 6,000 synthetic observations generated; train/calibration/threshold/holdout sizes 3432/432/432/1200 after maturation embargo. Both models exported with holdout parity verification.
- `scripts/local_verify.py`: launched actual HTTP server, ingested five synthetic scenarios, issued live recommendations, saved OpenAPI, and completed 150 concurrent benchmark requests.
- `scripts/browser_test.cjs`: Chromium checked login, dashboard, case update, model selection, assessment submission and mobile layout. Screenshots included.

Detailed values are in reports/evaluation.json, reports/benchmark.json, reports/tests.xml, reports/browser-test.json and dependency audit reports. Synthetic metrics are not real-world fraud effectiveness estimates. Browser checks do not constitute a complete accessibility assessment.

SQLite Alembic migration, backup integrity and restored schema version were also verified; see reports/migration-backup.json.

No real operator service, production OIDC, PostgreSQL server, Redis server, Kafka broker, remote MLflow/S3, Docker image, Kubernetes cluster or CI runner was exercised. Corresponding adapters have local/mock checks only where listed. The remaining release gates are explicit in PRODUCTION_READINESS.md.
