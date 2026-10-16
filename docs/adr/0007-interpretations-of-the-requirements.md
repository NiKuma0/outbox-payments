# ADR 0007: Interpretations of ambiguous requirements

- Status: accepted
- Date: 2026-10-16

Smaller decisions where the brief allowed more than one reading.

| Topic | Decision | Why |
|-------|----------|-----|
| Missing/invalid `Idempotency-Key` | `400` problem, key = 1-255 printable ASCII chars without spaces | IETF `draft-ietf-httpapi-idempotency-key-header` uses 400 for a missing key; 422 stays reserved for body validation |
| Same key, different body | `409` (as required) | The draft suggests 422; the brief explicitly asks for 409 |
| Request equivalence | sha256 over canonical JSON of the *validated* body (`"100"` == `"100.00"`, metadata key order ignored, list order significant) | Cosmetic differences must not turn a legitimate retry into a conflict |
| Amount input | JSON string or number accepted, always serialized as a string; fractions of a cent rejected, never rounded | Silently changing an amount is worse than a 422 |
| Auth on probes | `/health` and `/ready` are unauthenticated | Orchestrators call probes without credentials; they expose nothing sensitive |
| `/ready` | Checks database **and** broker (as required) | Compose healthchecks use `/health` for the API, so a broker outage never takes the API out of rotation. In Kubernetes readiness should drop the broker check: the outbox exists precisely so the API works without it |
| `PaymentProvider.charge` | `charge(payment_id, money)` | `payment_id` is the gateway idempotency key as required; a real gateway also needs the amount |
| Webhook payload | `payment_id`, `status`, `amount`, `currency`, `metadata`, `processed_at`; header `X-Webhook-Id` = event id | Metadata lets clients correlate with their orders; the id is stable across redeliveries for receiver-side dedup |
| Webhook redirects | Not followed, classified as permanent (DLQ) | A redirect is an SSRF vector |
| `webhook_delivered_at` | Stored on the payment, not exposed by the API | It is the consumer's checkpoint, not part of the contract |
| SQLAlchemy version | 2.1.x with the 2.0-style API | "2.0" read as the API generation; nothing used is 2.1-specific |
| Enums in Postgres | `VARCHAR` + `CHECK` | Native enum changes are awkward migrations |
| Migrations healthcheck | Disabled; dependants use `service_completed_successfully` | A one-off job has no meaningful "healthy" state |
| Worker healthchecks | Heartbeat file touched while `broker.ping()` succeeds | No HTTP port in relay/consumer, no curl in the slim image |
| Tests database | Integration tests use a separate `payments_test` database on the compose Postgres | Running tests never wipes demo data |
