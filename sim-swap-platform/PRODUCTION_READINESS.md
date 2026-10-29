# Production readiness — release 0.1.0

**Decision: NO-GO for live automated enforcement. GO for isolated demonstration and controlled staging evaluation.**

This is working source code with real local verification. It is not a certified full production system. Some requested enterprise capabilities require additional engineering as well as external access. The distinctions below are part of the deliverable, not optional warnings.

## Delivered and verified locally

- FastAPI authenticated API, tenant provisioning and scoped data access.
- Strict event schemas, HMAC identifier storage, duplicate detection and atomic batches.
- Shared point-in-time features using event and ingestion clocks.
- Rules recommendations, explicit unavailable signals, action binding, expiry and reassessment checks.
- Case generation/investigation, evidence-based supervised labels and label correction history.
- Policy simulation and different-person approval, audited restore of earlier policies.
- Logistic/XGBoost training, chronological splits, label-maturity embargo, calibration/validation/holdout separation, reports and native export parity.
- Safe JSON shadow scoring, incompatible/corrupt/missing artifact rejection and rules fallback.
- Signed webhook/outbox semantics verified with mocked external delivery.
- Tenant HMAC audit-chain integrity and operational purge behavior.
- Frontend TypeScript/build and browser workflow checks.
- Actual local HTTP concurrency benchmark against SQLite and synthetic provider.
- Python and frontend dependency vulnerability audits with zero known findings at verification time.

The test suite is 42 checks in this release. It uses real local SQLite and an in-process HTTP test client; external operator calls and webhook responses are mocked. The separate local benchmark and browser checks use a real launched HTTP server. See reports for the exact recorded evidence.

## Implemented but not live integration-tested

| Capability | Code/config delivered | Validation still required |
|---|---|---|
| PostgreSQL | SQLAlchemy backend, migration, Compose | Locking/concurrency/restore and database least privilege |
| Redis | Atomic rate-limit counter, readiness and explicit outage response | Real Redis failure/recovery, credential/TLS configuration |
| CAMARA | Pinned 2.1.0 `/check` adapter, timeout/circuit and unknown states | Actual operator OAuth/consent, privacy window, contract and quota acceptance |
| OIDC/MFA | RS256 JWKS verification, claims, human MFA requirement | Real issuer, key rotation and client identity lifecycle |
| Kafka | At-least-once bridge, commit discipline and DLQ pointers | Broker recovery, ACLs, partition/rebalance and replay exercises |
| Outbound webhook | Durable outbox, HMAC, retries, dead letter and replay | Real receiver deduplication and TLS/secret rotation |
| MLflow/S3 | Publishing utilities | Actual remote tracking/storage, private ACLs and model registry approval |
| OpenTelemetry | Optional instrumentation and sensitive-route exclusions | Collector, data minimization and trace pipeline review |
| Docker/CI | Compose, image build, scan/SBOM workflow | Actual image build and CI execution; signed/pinned images/actions |
| Kubernetes/Terraform | Application/namespace scaffolds | Complete environment, secrets/PVC/TLS/network controls and staging rollout |

Docker and cluster binaries/services were unavailable in the authoring environment. Local source tests are not evidence that these services have been deployed or passed their real integration checks.

## Requested capabilities not completed in this release

1. **Active validated ML decisioning, model approval workflow and canary automation.** Models are shadow-only; `fraud_probability` remains null. No automatic model promotion is implemented.
2. **High-volume online feature store/caching and efficient query architecture.** Redis is used for rate limiting, not feature caching. JSON tenant record scans and serialized transactions must be replaced/benchmarked for telecom-scale traffic.
3. **Geographic, retail-agent, linked-account/graph and dedicated device-change analytics.** Authorized fields/events may be ingested, but these advanced predictive features are not implemented.
4. **Operator subscription callbacks, number verification, device-swap and banking enforcement adapters.** `/check` is the only operator API implemented; external account holds/blocks are not performed.
5. **Customer-facing recovery/appeal and independent verification integrations.** Recommended factors and audited supervisor override exist; customer workflows remain external.
6. **Enterprise dashboard SSO/PKCE and account/session administration.** The browser accepts an already-issued token and holds it in memory.
7. **Immutable audit checkpoints, full data/backup/training deletion orchestration, label dual approval and automatic retention scheduling.** Current HMAC chain and operational purge do not satisfy these broader requirements.
8. **Sustained workload/broker backlog recovery/real-provider load testing, production disaster recovery and independent penetration testing.** Brief local concurrent HTTP testing is delivered, not a production SLA.
9. **Complete production Terraform/environment provisioning and dashboard provisioning for Grafana.** Scaffolds and metric/tracing endpoints are supplied, not a hosted operational cluster.
10. **Automated delayed-label performance/calibration monitoring and scheduled retraining approval.** Offline reports, feedback export and PSI drift utility exist; an operational scheduler/promotion governance remains to be implemented.

## External release gates

Before real deployment, the owner must provide/approve:

- Authorized operator/bank contracts and access; real integration specifications.
- Legally obtained representative historical data with mature adjudicated labels.
- Investigation-selection/label-noise assessment, cohort coverage, customer false-positive cost and recovery capacity.
- Business-approved evaluation thresholds and independently reviewed results.
- Strong identity mappings and source-specific ingestion entitlements.
- Environment TLS/encryption, managed secrets, backup keys and minimal DB permissions.
- Regulatory/consent/data-sharing/retention review for the actual jurisdiction.
- Signed artifact/image provenance, vulnerability/secret/image scans and independent security review.
- Live infrastructure/integration acceptance, restore drill and sustained load/fault recovery testing.
- Monitored shadow operation, approved customer verification and explicitly authorized enforcement integration.

Production configuration validation enforces several prerequisites but is not a certification. No production approval is implied by successful startup or a high synthetic model metric.
