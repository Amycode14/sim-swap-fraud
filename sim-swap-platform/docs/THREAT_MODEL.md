# Threat model and security boundary

## Assets and trust boundaries

Assets include subscriber/account pseudonyms, network signals, assessments, analyst evidence, labels, signing keys and model artifacts. The operator/bank event source, identity provider, API, database, dashboard browser, broker, model filesystem and webhook receiver are separate trust boundaries.

| Threat | Implemented defense | Remaining deployment requirement |
|---|---|---|
| Unauthenticated lookups | Signed/expiring bearer tokens and backend scopes | Enterprise browser OIDC flow; identity lifecycle and revocation |
| Cross-tenant access | Tenant claim verification, provisioning check, scoped database queries, tenant HMAC | PostgreSQL RLS and integration tests against real tenant workloads |
| Forged or replayed events | Scoped integration role, strict schema, stable event IDs, conflicting-payload rejection | Source-specific allowlists, mTLS/provider webhook verification |
| Compromised SIM receives OTP | Independent step-up options; no SMS-only recommendation | Actual trusted-device/passkey/customer recovery integrations |
| Insider adjudication abuse | Supervisor roles, evidence references, label history, audit | Label dual approval and independent case quality review |
| Policy abuse | Different proposer/approver, simulation and audited activation | Enterprise change-control ticket binding and approval expiry |
| Model poisoning/replacement | Safe native JSON, schema compatibility, SHA-256, shadow-only use | Signed manifests, access-controlled registry, real training-data validation |
| Webhook tampering | HMAC signature, timestamp verifier, durable outbox, event IDs | Receiver durable event-ID deduplication; key rotation; approved destinations |
| Data leakage | Identifier HMAC, tenant scope, masked UI, strict no-OTP attributes | Encrypt DB/backups; redact proxy logs; prohibit PII in notes; protect exports |
| Dependency compromise | Exact dependencies, audit reports, CI scan steps | Signed images/actions, SBOM attestation, ongoing vulnerability review |
| Denial of service | Rate limits, request-length check, bounded event batches, provider timeout | Proxy body/connection caps, network policy, tenant quotas and load validation |
| Audit modification | Tenant-serialized HMAC chain | Append-only DB grants plus immutable external checkpoint/retention |

The audit chain detects modified entries with the current key. A database administrator with signing-key access can rewrite it, and deleting the tail cannot be detected without an external checkpoint. It is not an immutable WORM store. Audit-key rotation requires an explicit chain-version migration and preserved verification keys.

The demo bearer issuer is only a local development tool. Outside demo, the API verifies RS256 signatures, issuer, audience, expiry and required tenant/role claims from the configured identity provider. Humans require an MFA/hardware-key claim. Service tokens need controlled client identities and lifetimes. Service credential rotation and user login/logout flows remain identity-provider responsibilities.

No real customer SMS content, OTP, PIN, authentication secret or IMSI/ICCID is required. Strict attributes prohibit arbitrary extra properties. `note` and `evidence` fields are still free text: operational policy and DLP review must prevent staff from inserting sensitive contents.

Retention is not automatic in this release. The privileged operational purge endpoint deletes linked operational rows but explicitly reports pending training-artifact erasure. Training exports, backups, S3 versions and audit retention need a separate approved legal policy. Do not represent the purge endpoint as complete regulatory erasure.
