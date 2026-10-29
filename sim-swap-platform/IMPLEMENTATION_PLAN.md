# Implementation milestones

| Milestone | Delivered | Remaining gate |
|---|---|---|
| 1. Requirements and architecture | Original spec retained; architecture, threat model and integration boundary documented | Real operator/business cost/throughput requirements |
| 2. Ingestion and identity | Working strict-schema API, tenant scope, demo JWT issuer, OIDC verification, HMAC identifiers, atomic batches | Real OIDC/MFA acceptance and authorized operator source mappings |
| 3. Features and rules | Shared point-in-time features, action-bound assessment, fallback policy, auto cases | Geographic/agent/link analysis and high-volume feature store |
| 4. ML training | Logistic/XGBoost/rules comparison, calibration split, holdout, reports, native export parity | Representative real mature labels and independent evaluation |
| 5. Inference/governance | Safe JSON shadow scoring, checksums, fallback, policy simulation/two-person approval | Signed registry, active-ML approval, canary controller |
| 6. Dashboard/cases | React dashboard, queues, details, timeline, investigation, labels, policies, shadow registry, audit | Enterprise SSO browser flow, accessibility audit, customer recovery UI |
| 7. Operations | Compose, migration, outbox, Kafka bridge, S3/MLflow publishing, OTel instrumentation, CI, deployment scaffolds | Live cluster validation, managed secrets, TLS, network policies, monitored recovery exercise |
| 8. Verification/download | Tests, synthetic evaluation, dependency audits, local HTTP benchmark, source/download package | Full PostgreSQL/Redis/broker/container/remote integration suite and production security review |

No production deployment, real subscriber data access, external message delivery or account enforcement was performed. The readiness report contains exact limits; delivery is a runnable reference release rather than a completed certified production service.
