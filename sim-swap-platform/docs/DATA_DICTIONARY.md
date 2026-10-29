# Data dictionary

Every operational row has an internal UUID, verified tenant, record kind, tenant-unique key, revision, UTC created timestamp, and canonical JSON body. JSON bodies are schema-validated at ingress. There is no database foreign-key cascade; application purge handles related rows explicitly.

| Entity | Required fields | Meaning |
|---|---|---|
| Event input | event_id, source, subscriber, event_time, event_type | Stable source ID; authorized source; pseudonymized subscriber; timezone-aware timestamp; supported type |
| Event storage | ingested_at, payload_hash, quality, schema_version | Arrival time; conflicting replay detection; late/timely flag; schema 1 |
| Attributes | All optional except default currency | device_id, beneficiary_id, agent_id are pseudonymized; amount is bounded finite nonnegative; currency ISO-style 3 letters; country 2 letters; trusted_device and constrained reason |
| Assessment input | subscriber, action_id, action | Specific operation binding; pre/post mode; optional device, amount, currency, beneficiary |
| Assessment output | assessment_id, context, assessed_at, expires_at, risk_score, recommendation | Immutable snapshot of the assessed operation, finite validity and heuristic recommendation |
| Assessment provenance | feature_version, policy_version, model_version, signal, features | Complete versioned decision context; no fraud probability claimed |
| Signal | status, observed_at, source | Availability and provenance; monitoring_hours/latest_change only when genuinely supplied |
| Case | case_id, assessment_id, status, version, notes | Investigation record linked to decision; optimistic concurrency and notes |
| Case label | label, label_provenance, label_history | 1 fraud / 0 legitimate only after supervised evidence-based adjudication; null unresolved/disputed |
| Policy | ordered thresholds, fallback, TTL, version, proposed_by, approved_by | Two-person approved rule threshold policy |
| Audit | sequence, actor, action, target, detail, previous_hash, hash | Per-tenant HMAC chain; administrative external checkpoints still required |
| Outbox | event_id, type, payload, status, attempts, next_attempt | Transactionally durable minimal notification metadata; retry/dead-letter state |

Supported event types: sim_request, sim_change, port, login, failed_login, recovery, beneficiary, transaction, device_change, legitimate_replacement, number_recycle. Some ingested event types provide timeline context but do not currently introduce a dedicated model feature.

Current API retention accepts up to 90-day-old incoming events and at most 60 seconds of future clock skew. Older training history is managed offline. The acceptance window is not an automatic data-deletion policy. Monetary baselines never mix currencies; international FX conversion is not implemented.

Labels and investigation outcomes never enter `build_features`. For historical training, both event_time and ingested_at must qualify; mature labels are filtered at the training split boundary. Feedback export deliberately excludes unresolved cases and warns that investigated samples are a selected cohort.
