# SIM Shield — SIM Swap Fraud Detection Platform

A runnable reference implementation with a FastAPI API, React analyst dashboard, tenant-scoped ingestion, a rules decision engine, and a reproducible machine learning pipeline.

**Release status: working demonstration/reference implementation, not approved for live production enforcement.** The supplied training data and models are synthetic. There are no real subscriber records, operator credentials, default passwords, or account-blocking integrations in this package. Read `PRODUCTION_READINESS.md` before connecting real services.

## Quick start: Windows

Install **Python 3.12**. Unzip this project, open PowerShell in its folder, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
```

The script creates a virtual environment, installs the locked dependencies, creates independent local secrets, prints a two-hour demo access token, and starts the application.

Open **http://127.0.0.1:8000** and paste that token. Keep this terminal open. Press Ctrl+C to stop the server. The dashboard is already built; Node.js is only required when changing its source.

## Quick start: Linux / macOS

Use Python 3.12; run from the extracted project folder:

```bash
bash start_demo.sh
```

Dependency installation requires internet access and can take several minutes. Native ML wheels are substantial; this archive does not bundle a Python interpreter or Python wheels. The transitive lock was validated on Linux CPython 3.12; verify native-wheel availability on other operating systems.

## Populate the dashboard

In a second terminal, generate another token and load synthetic scenarios:

```bash
# Linux/macOS
.venv/bin/python scripts/issue_demo_token.py
.venv/bin/python scripts/seed_demo.py --token YOUR_LOCAL_TOKEN

# Windows
.venv\Scripts\python.exe scripts/issue_demo_token.py
.venv\Scripts\python.exe scripts/seed_demo.py --token YOUR_LOCAL_TOKEN
```

Replace `YOUR_LOCAL_TOKEN` with the issued token; never commit tokens or `.env`. Demo seed runs use fresh synthetic subscriber IDs, so repeating them does not accidentally increase replacement counts for previous scenarios.

| Scenario | Default expected recommendation |
|---|---|
| Ordinary known-device login | ALLOW |
| Legitimate eSIM replacement followed by known-device login | ALLOW |
| Recent swap followed by unfamiliar-device account recovery | REVIEW |
| Recent swap followed by new beneficiary and unusual transfer | TEMPORARY_HOLD |
| Reassigned number, prior history discarded | ALLOW for the demonstration login; sensitive actions use fallback |

These are heuristic policy examples, not guaranteed real-world fraud outcomes.

## Use a trained model

Two pre-trained **synthetic** model artifacts are included. In Models, select logistic regression or XGBoost for shadow scoring. Their scores are displayed alongside the authoritative rules result. They do not replace the policy or constitute validated fraud probabilities.

Reproduce training:

```bash
python ml/synthetic.py --count 6000
python ml/train.py
```

Training uses the same point-in-time feature builder as the API. It separates training, calibration, threshold selection, and holdout, purges overlapping campaign groups, and applies a label-maturation embargo. Reports include PR AUC, precision/recall, false positives, illustrative costs, subgroup metrics, and bootstrap confidence intervals.

## API examples

The full contract is in `docs/openapi.json`. Running API documentation is available at `/openapi.json`; `/docs` and `/redoc` depend on their documentation assets and the site's CSP, so prefer the included offline contract if the interactive viewer is blocked.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/events \
  -H 'Authorization: Bearer YOUR_LOCAL_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"network-event-1","source":"authorized-operator","subscriber":"+251911223344","event_time":"REPLACE_WITH_CURRENT_UTC_ISO_TIMESTAMP","event_type":"sim_change","attributes":{"reason":"replacement"}}'

curl -X POST http://127.0.0.1:8000/api/v1/assessments \
  -H 'Authorization: Bearer YOUR_LOCAL_TOKEN' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: unique-action-key-1' \
  -d '{"subscriber":"+251911223344","action":"transaction","action_id":"payment-1001","device_id":"new-device","amount":5000,"currency":"ETB","beneficiary_id":"new-beneficiary"}'
```

Assessment replay returns the original decision and original expiry. A client must not treat it as a new authorization. Use `/api/v1/assessments/{id}/validate` with the bound action ID/type. New events or expiry require a new assessment and new idempotency key.

## Docker with PostgreSQL and Redis

Generate `.env`, then:

```bash
python scripts/init_demo.py
docker compose up --build --wait
```

Open http://127.0.0.1:8000. Generate a token inside the API container:

```bash
docker compose exec api python scripts/issue_demo_token.py
```

The container issuer reads its injected demo configuration; the image does not copy `.env`. The demo issuer is not a production identity provider.

Optional webhook worker:

```bash
# First configure WEBHOOK_URL and a fresh WEBHOOK_SECRET in .env.
docker compose --profile webhooks up --build --wait
```

The optional streaming profile starts Redpanda. `scripts/kafka_bridge.py` consumes an authorized tenant topic and forwards events through the authenticated API. Configure the broker and integration token before running it; see `docs/INTEGRATIONS.md`.

**Docker, PostgreSQL, Redis, Kafka, Kubernetes and remote MLflow/S3 were not live-tested in the authoring environment.** Their configuration/adapters are supplied for staging verification, not as evidence of a tested production cluster.

## Verify

```bash
python -m pytest -q --junitxml=reports/tests.xml
python -m ruff check backend ml scripts
python scripts/local_verify.py
cd frontend
npm ci
npm run build
npm audit --audit-level=high
```

Browser workflow checks are in `scripts/browser_test.cjs`. Install Playwright and a Chromium browser before enabling `RUN_BROWSER_TESTS=true`. The script can use `CHROMIUM_EXECUTABLE_PATH` for an existing browser.

## Project map

| Folder/file | Purpose |
|---|---|
| `backend/app/` | API, access controls, storage, feature builder, rules, provider, model runtime, outbox |
| `backend/tests/` | Meaningful functional/security/failure-path checks |
| `frontend/src/` | React/TypeScript/Tailwind/Zustand analyst application |
| `frontend/dist/` | Pre-built dashboard for immediate startup |
| `ml/` | Synthetic observation generator and chronological training |
| `artifacts/` | Safe JSON model exports with checksums and manifests |
| `scripts/` | Startup, demo issuer/seed, benchmark, integrations, drift and backup utilities |
| `deploy/` | Alembic migration, Kubernetes scaffold, namespace Terraform scaffold |
| `reports/` | Actual measured evaluation, test, audit and benchmark results |
| `docs/` | Contracts, security and operational documentation |
| `PRODUCTION_READINESS.md` | Detailed implementation status and release blockers |

Local secrets are generated on your computer. The download excludes `.env`, local operational databases, tokens, caches, and node_modules.
