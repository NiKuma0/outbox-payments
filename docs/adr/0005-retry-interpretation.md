# ADR 0005: What "3 attempts with exponential backoff" means

- Status: accepted
- Date: 2026-10-16

## Context

The requirement says "3 attempts with exponential backoff, then a dead letter
queue", and the topology has exactly three retry queues (1 s, 4 s, 16 s). "Attempt"
could mean deliveries in total (3) or retries after the first one (3, so 4 in total).

## Decision

`MAX_RETRIES=3` is the number of **retries after the first delivery**:

| Delivery | Waited before | `x-retry-count` on arrival | On transient failure goes to |
|----------|---------------|----------------------------|------------------------------|
| 1        | -             | absent (0)                 | `payments.new.retry.1` (1 s) |
| 2        | 1 s           | 1                          | `payments.new.retry.2` (4 s) |
| 3        | 4 s           | 2                          | `payments.new.retry.3` (16 s)|
| 4        | 16 s          | 3                          | `payments.new.dlq`           |

Three retry queues are only meaningful if all three are used, which this reading
guarantees; `MAX_RETRIES=0` disables retries.

Classification (`entrypoints/consumer.py::is_permanent`):

- **Retry**: webhook 5xx, 408, 429, timeouts and connection errors; database or broker
  unavailable; and any *unexpected* exception. Retrying an unknown error is cheap and
  bounded by `MAX_RETRIES`; dead-lettering it on the first occurrence would turn every
  transient bug into manual work.
- **DLQ immediately**: malformed message, unknown payment, webhook 4xx other than
  408/429, and 3xx (redirects are never followed: SSRF).
- **Neither**: a gateway decline. It is a business outcome: status `failed`, webhook
  sent, message acked.

## Consequences

- Worst case a message takes 1 + 4 + 16 = 21 s of delays plus four processing
  attempts before reaching the DLQ (the e2e test allows 60 s).
- A non-numeric `x-retry-count` is treated as exhausted, so header corruption can
  never cause an infinite loop.
- DLQ messages carry `x-retry-count`, `x-last-error` and `x-failed-at`, plus the
  original `message_id` (= event id) and body, so they can be replayed by shovelling
  them back to `payments.new`.
