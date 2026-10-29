# Operations runbook

## Local reference

Use `start_demo.sh` or `start_demo.ps1`; listener is loopback only. Keep `.env` private and out of source control. Python 3.12 is the validated interpreter. The dashboard build is bundled. Rebuild with Node.js 24, `npm ci` and `npm run build` when editing frontend source.

## Proposed staging budget

Initial targets to validate, not claimed SLAs: internal feature/rule assessment p95 below 100 ms on indexed storage; end-to-end p95 below 500 ms excluding a separately measured provider budget. Provider check timeout is 2 seconds. Suggested initial availability target 99.9%, subject to operator service guarantees and policy. Real targets and RTO/RPO must be approved with business owners.

Local benchmark results in reports/benchmark.json measure a brief synthetic-provider SQLite run. They do not validate these proposed targets, production sustained throughput, operator API latency or high availability.

## Staging infrastructure

Start with 2 CPU / 4 GiB RAM for a small demonstration plus PostgreSQL/Redis; allocate extra disk/memory for native XGBoost dependencies. This is an initial estimate, not measured production sizing. ML training should run separately from the inference API. Load test representative event/history sizes before selecting capacity.

The Compose default is local-only. PostgreSQL/Redis/broker ports are not publicly published. Containers use demo identity and no real data. Production needs managed TLS ingress, secret management, hardened database permissions, encryption, broker TLS/ACLs, backups, tenant quotas and private egress allowlists.

The supplied Kubernetes manifest and Terraform file are **scaffolds**. Terraform creates only a namespace. It does not provision a cloud environment, secrets, database, Redis, ingress, PVC or a production identity provider. Replace the image placeholder with an approved digest, create the referenced secret/PVC, and stage-test the manifests before use. Pin provider/image digests and establish a Terraform lockfile in your target deployment.

Run explicit schema migration before starting non-demo API:

```bash
DATABASE_URL='YOUR_APPROVED_URL' python -m alembic -c deploy/alembic.ini upgrade head
DATABASE_URL='YOUR_APPROVED_URL' python scripts/provision_tenant.py your_tenant_id
```

Use environment injection/secret management in real environments rather than command-line secrets. Production APP_ENV refuses demo provider/SQLite and incomplete OIDC/Redis/real provider configuration. This check does not itself establish release readiness.

## Outage handling

- Provider timeout/outage: preserve unavailable status; independent step-up/review for sensitive actions. Circuit opens after three failures for 30 seconds. No live clean signal is fabricated.
- Missing or invalid model: use rules; model_error/fallback_used visible; shadow cannot authorize actions.
- Redis unavailable: authenticated API returns 503; do not bypass rate limiting in production.
- Database unavailable: no assessment is issued; readiness fails and requests return 503 where database exceptions are caught. Client retries require the same idempotency key until outcome is known.
- Broker/API outage: bridge retains offsets; renew integration token before restart when expired. Broker DLQ keeps pointers and hashes for approved replay.
- Webhook failure: pending outbox retries; after eight failures dead-letter; investigate receiver and signing configuration before supervised replay.

## Recovery and customer friction

Assessment recommendations expire; clients must validate the bound action and reassess when expired or new events appear. The platform does not hold or unhold actual bank accounts. Independent verification and customer appeal are external workflows. Supervisors can record a verified override with a reference; an expired assessment cannot be overridden into a fresh approval.

## Backup/restore

For SQLite demonstration:

```bash
python scripts/backup_sqlite.py --destination data/backup-UNIQUE_TIMESTAMP.db
```

The utility uses SQLite's online backup API and checks integrity. To restore, stop the server, preserve the current database for incident evidence, restore the approved backup to data/platform.db, retain the corresponding authentication/pseudonymization keys securely, and run readiness/audit verification before serving requests.

For PostgreSQL use an approved encrypted pg_dump or managed snapshot/PITR policy, with least-privilege backup credentials. Restore to an isolated staging database and verify tenant counts, sample features, event idempotency, audit chains and outbox state. A restore can replay already-delivered webhooks; receiver deduplication is mandatory. No live PostgreSQL restore drill was performed here.

Keep model artifact copies and manifests in versioned private storage; verify checksums on restore. Backups and encryption keys must have independent access/retention policies. Do not rotate the audit key without a chain-version/key-history migration.

## Incident response

Restrict compromised integration credentials; preserve source pointers and audit checkpoints; suspend suspicious source ingestion or shadow model selection; use rules and conservative recovery policies; identify affected assessments by time/source/version; notify authorized incident owners through your approved channel. Customer communications and external notifications are not automatically sent by this project.

## Release procedure

Pass API/security tests, frontend build, dependency/image/secret scans and SBOM generation. Then execute PostgreSQL/Redis/broker/provider/identity/worker end-to-end tests, concurrency and sustained load tests, restore drill, independent penetration review and shadow operation using real authorized data. Record business-approved false-positive/recall/cost targets and customer recovery capacity before any enforcement integration.
