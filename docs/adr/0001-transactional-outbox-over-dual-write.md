# ADR 0001: Transactional outbox instead of dual write

- Status: accepted
- Date: 2026-10-16

## Context

Creating a payment has two side effects: a row in Postgres and an event on
RabbitMQ. Two independent systems cannot commit atomically without 2PC, which
RabbitMQ does not offer. Every "dual write" ordering has a failure window:

| Order                       | Crash between the two writes                         |
|-----------------------------|------------------------------------------------------|
| commit, then publish        | payment exists, nobody ever processes it             |
| publish, then commit        | consumer sees an event for a payment that never was  |
| publish inside the DB tx    | commit fails after the publish: same as above        |

The API must also keep accepting payments while the broker is down.

## Decision

Write the event to an `outbox` table **in the same transaction** as the payment.
A separate relay process polls the table (`FOR UPDATE SKIP LOCKED`), publishes with
publisher confirms, marks rows `published_at`, and commits.

## Consequences

- Atomicity comes from Postgres alone: a payment exists iff its event exists.
- The API has no runtime dependency on RabbitMQ; a broker outage only delays
  processing (covered by an e2e test).
- Delivery is **at-least-once**: a relay crash after the broker confirm but before
  the commit republishes the batch. Consumers must be idempotent (they are, see the
  consumer state machine in `docs/ARCHITECTURE.md`).
- Polling adds latency (`RELAY_POLL_INTERVAL_SECONDS`, 0.5 s default) and steady
  load on Postgres; the partial index `WHERE published_at IS NULL` keeps each poll
  an index-only scan of the backlog. CDC (Debezium on the WAL) removes both and is
  the production upgrade path.
- Published rows are purged after `OUTBOX_RETENTION_DAYS`.
- Global ordering is not guaranteed across relay replicas; nothing here needs it
  (each payment has exactly one event).
