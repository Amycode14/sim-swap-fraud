# External integration guide

## CAMARA SIM Swap

Target contract: public SIM Swap 2.1.0, release r3.2/r3.3. The adapter implements `/check` only. Set `PROVIDER_MODE=camara`, `PROVIDER_URL` to the **approved operator base URL including the contract path**, `PROVIDER_TOKEN`, and `PROVIDER_CONTRACT_VERSION=2.1.0`.

Example request shape is `{"phoneNumber":"+251…","maxAge":24}`. The adapter expects a boolean `swapped`. True means a change within the window. False means no change within the supported window, not a lifetime clean history. The adapter intentionally returns unknown for a pseudonymous identifier because it cannot reverse a pseudonym into an operator phone number.

Before activation, verify operator access, OAuth/consent scope, phone-number format, privacy minimum monitoring windows, returned error codes, latency/rate quotas, subscriber authorization and contract test fixtures. Missing/null/invalid response becomes outage; unsupported operations are explicit; three consecutive failures open a 30-second circuit. There are no invented Ethio telecom/Safaricom/bank URLs or claims that an operator exposes this API.

Bearer-token refresh, callbacks/subscriptions, `/retrieve-date`, number verification and device swap are not integrated. Use authenticated ingestion for authorized SIM/port/device events when your provider supplies those sources. This archive does not include an operator data-access entitlement.

## OIDC

Outside demo, configure OIDC_ISSUER, OIDC_AUDIENCE and OIDC_JWKS_URL. Trusted claims: `sub`, `tenant`, `role`, `iat`, `exp`; human tokens also require `amr` with `mfa` or `hwk`. Roles are administrator, supervisor, analyst, auditor and integration. Claim mappings must be administered at your issuer; never allow a browser to select an arbitrary tenant or role.

The dashboard accepts an existing bearer token. Implement your provider's authorization-code-with-PKCE login and controlled token lifecycle before exposing it to real users. For service integrations use issued scoped client credentials, not the demonstration issuer.

## Kafka bridge

Install `requirements-integrations.txt`. Configure KAFKA_BOOTSTRAP, KAFKA_TENANT, KAFKA_TOPIC, API_URL and INTEGRATION_TOKEN. Production brokers need SASL_SSL; configure KAFKA_SASL_USERNAME/KAFKA_SASL_PASSWORD. Each bridge token is bound to a provisioned tenant. Authorize topic access accordingly.

Run `python scripts/kafka_bridge.py`. Source messages follow EventIn in the OpenAPI contract. Consumer offsets are committed synchronously only after successful ingest or acknowledged DLQ metadata publication. Retryable API/broker outages retain the offset. Invalid JSON stops the bridge for operator remediation. Authentication failure stops without committing.

The DLQ contains a source partition/offset and SHA-256, not a duplicate raw customer payload. Approved operators can inspect the source and replay a corrected event with a new stable ID when needed; event deduplication protects ordinary replay. Source retention must exceed recovery objectives. Broker fault recovery and quotas need live validation.

## Signed outbound webhooks

Configure an administratively approved WEBHOOK_URL and WEBHOOK_SECRET; the endpoint is not caller-controlled. Outside demo HTTPS is mandatory. Run `python -m backend.app.worker` with configured environment. The worker signs `<timestamp>.<raw JSON bytes>` with HMAC-SHA256 and sends X-Signature, X-Signature-Timestamp and X-Event-ID. Verify signatures before parsing and reject timestamps beyond five minutes using `verify_webhook`.

Receivers must persist event IDs to prevent duplicate processing inside the freshness window. Eight failures produce a dead-letter record. A supervisor can reset a dead-letter through `/api/v1/outbox/{id}/replay`. Delivery is at least once; a crash after receiver success but before commit causes replay. Outbox events contain minimal assessment metadata, not raw subscriber identifiers. Run one worker in this release; high-volume deployments need leasing and bounded lock-free delivery.

## MLflow and S3

`python scripts/publish_models.py --mlflow` publishes experiment/run metadata and evaluation metrics through MLflow REST. Set MLFLOW_URL and optional MLFLOW_TOKEN. It does not create a remotely approved model version or implement automatic promotion.

`python scripts/publish_models.py --s3` uploads JSON artifacts/reports under content-addressed prefixes. Configure S3_BUCKET, optional S3_ENDPOINT/S3_PREFIX and the AWS SDK's credential chain. Uploads request server-side AES256 encryption. Configure versioning, IAM, private access, lifecycle, object locks and integrity verification independently. No S3 or MLflow service was contacted during this delivery.

## Observability

Set OTEL_ENABLED=true and OTEL_EXPORTER_OTLP_ENDPOINT to enable OTLP HTTP tracing. Prometheus metrics are at `/metrics` and require an auditor/admin bearer token. Metrics include assessment recommendation counts and complete assessment latency, without customer identifiers as labels. Configure a secured scrape token and collector outside the archive.

Geographic, retail-agent and linked-account feature integrations are intentionally not simulated as real signals. Add them only with authorized schemas, proven provenance and point-in-time tests.

## Primary references checked during implementation

- CAMARA release/spec: https://github.com/camaraproject/SimSwap/releases and https://github.com/camaraproject/SimSwap/blob/r3.2/code/API_definitions/sim-swap.yaml
- NIST authentication guidance: https://pages.nist.gov/800-63-4/sp800-63b.html
- FastAPI security: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- Scikit-learn calibration: https://scikit-learn.org/stable/modules/calibration.html
- Confluent Python client: https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html
- MLflow REST: https://mlflow.org/docs/latest/api_reference/rest-api.html
