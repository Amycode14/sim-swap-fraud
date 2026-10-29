# System architecture and implementation notes

## Architecture

The dashboard calls the versioned FastAPI API on the same origin. OIDC or the isolated local demo issuer provides authenticated tenant/role claims. Ingestion validates a strict event schema, pseudonymizes identifiers with a tenant-bound HMAC, and persists the event and audit entry in a transaction. Assessments load eligible historical events, optionally query CAMARA, build point-in-time features, apply a versioned policy, optionally score a shadow model, and persist the assessment, case, audit entry and outbox together.

SQLite is the local reference store. Docker configuration uses PostgreSQL and Redis. A single outbox worker delivers signed webhooks with retries and dead-letter handling. The optional Kafka bridge commits source offsets only after API ingestion or durable DLQ acknowledgement. It is at-least-once; event IDs provide deduplication. Neither mechanism claims distributed exactly-once delivery.

## Tenant boundaries

The tenant comes from verified token claims and must already be provisioned. All database queries include it. Identifiers are tenant-bound. PostgreSQL tenant-row locks serialize transactional audit chain/outbox writes; the SQLite demo also serializes requests with a process-local lock. Outside demo, model artifacts are read from `ARTIFACT_DIR/<tenant>/`. Demo artifacts are shared synthetic examples with no tenant customer data.

The JSON-record schema is deliberately inspectable but not optimized for large telecom traffic. Assessment/event listings scan tenant records and materialize some results in memory. Typed indexed event tables, pagination/aggregation queries, event partitioning, and a dedicated feature store are required for high-volume service. See the release gates.

## Signal semantics

Provider status is one of recent_change, no_change_in_window, unknown, unsupported, stale, timeout or outage. A negative check means no change inside the requested monitoring window only. A null/non-boolean provider result is unavailable, not clean. /check never invents an exact swap time. Provider failures trigger a bounded circuit breaker. Exact historical event times remain useful even when the provider is unavailable.

The CAMARA adapter targets public SIM Swap API 2.1.0 `/check` request/response semantics. It requires an operator base URL and an authorized bearer token. It does not implement consent authorization, OAuth refresh, operator subscriptions, number verification, device swap or number porting APIs. Porting can instead arrive as an authorized event. Provider-specific access and contracts must be staged and verified.

Pre-replacement assessments only accept `action=sim_replacement`; other actions use post-replacement mode. The model and rule features use only already-ingested history, never the eventual result of the replacement under review.

## Feature schema v1

Features: sim_age_hours, sim_changes_24h, requests_24h, port_recent, new_device, recovery_recent, new_beneficiary, failed_logins_1h, transactions_1h, amount_ratio, tenure_days, signal_missing, trusted_device, cold_start, network_recent.

Both event_time and ingested_at must precede the assessment timestamp. New-number recycling severs preceding history. Monetary comparisons use historical transactions of the same currency. Sparse history is explicit. `trusted_device` is a diagnostic assertion from an authorized source, never sufficient to negate strong signals. Geographic, agent and cross-account relationship features are not implemented in this release; country and agent fields are ingested for future authorized development.

## Decision semantics

Risk_score is a 0–100 heuristic sum, not a probability. Thresholds are configurable and ordered. Strong recent-change + recovery/beneficiary/device/amount signals increase risk. Unknown network signals lead to independent step-up for sensitive actions even when the numeric score is low. Legitimate replacement alone does not block a customer.

Rules authoritatively drive recommendations. Synthetic model outputs are shadow scores. `fraud_probability` remains null. The training report evaluates separate calibration, but native runtime shadow scores are raw model outputs; this distinction is intentional and documented.

Recommendations never call a telecom or bank enforcement API. Clients must bind to the action, check expiry and new events, and enforce only through separately approved policies/integrations. Temporary holds are recommendations with expiry, not actual account freezes. BLOCK_RECOMMENDATION is available through an audited supervisor override, not automatically emitted by default rules.

## Case management

Review/hold decisions automatically open cases. Analysts add notes and move investigations through non-final states. Supervisor permission is required for confirmed labels, disputes or reopening a resolved case. Adjudication requires evidence references; corrections preserve label history and actor/time provenance. Unresolved/disputed cases are not treated as legitimate labels. Investigation notes are access controlled but user supplied; operators must ensure staff do not paste unnecessary personal data.

## Governance

Policy proposals are simulated against stored assessments and require a different supervisor for activation. Re-approving an earlier proposal restores it and writes an audit entry. Model selection/rollback is shadow-only; there is no active-ML promotion or production canary controller. Artifact checksums detect file corruption; they are not a replacement for signed build/artifact provenance and a protected registry.

## Model evaluation

The synthetic generator produces events, decision context, operator/scenario metadata and mature labels. Training uses the shared builder; feature parity and safe native model export parity are checked. Campaign IDs are disjoint across splits. Synthetic subscribers are unique, so returning-subscriber generalization is not measured. Class weighting is applied only in training. Thresholds minimize documented illustrative costs on validation. Holdout metrics, subgroups and bootstrap PR-AUC intervals are reported without claiming real effectiveness.

Optional Isolation Forest diagnostics do not affect decisions. Drift is an offline PSI report and never promotes a model or blocks a customer. Delayed production calibration/outcome monitoring needs adjudicated real data and an operational schedule.

## Configuration and lifecycle

`Settings.validate()` rejects weak/matching secrets and rejects demo providers/SQLite/missing OIDC or Redis in production. Production human JWTs require MFA/hardware-key claims. Provision tenant identities administratively. Outside demo, run Alembic explicitly before deployment; automatic table creation is disabled.

Metrics exclude subscriber/tenant labels. Optional OpenTelemetry excludes sensitive identifier-bearing routes. Reverse-proxy access logging must redact query strings and identifiers. Local console access logs can include routes, so disable them when using real data.

Keep this document and the readiness report current whenever code, features, policies, schemas or integration behavior changes.
