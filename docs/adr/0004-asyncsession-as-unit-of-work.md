# ADR 0004: `AsyncSession` is the unit of work; use cases commit explicitly

- Status: accepted
- Date: 2026-10-16

## Context

`CreatePayment` must write the payment and its outbox record atomically;
`ProcessPayment` must commit at well-defined checkpoints. A hand-written
`UnitOfWork` class would wrap `AsyncSession`, which already *is* a unit of work
(identity map, one transaction, commit/rollback).

## Decision

- The application layer depends on a one-method port, `Transaction.commit()`.
  `AsyncSession` satisfies it structurally and is passed in directly.
- Repositories receive the same session, so everything a use case does shares one
  transaction.
- **The use case calls `commit()` before returning.** Dependency teardown only closes
  the session (rolling back anything uncommitted).

## Consequences

- No wrapper class to maintain; SQLAlchemy semantics are not hidden.
- Committing in a FastAPI dependency's teardown would be wrong: teardown runs after
  the response is produced, so a failed commit could follow a `202 Accepted` for a
  payment that does not exist. Committing inside the use case makes "202 implies
  durable" true by construction (unit-tested with a mocked commit that raises).
- `ProcessPayment` commits twice (after the charge, after the webhook). Those commits
  are exactly the resumption points of the consumer state machine.
- Rollback is implicit (session close). The application has no way to roll back
  explicitly, and does not need one: raising is enough.
- `expire_on_commit=False`, so objects remain usable after commit without lazy loads
  (which would fail in async code anyway).
- Unit tests mock `Transaction` and the repositories; the transactional behaviour
  (rollback on close, isolation, row locks) is verified on real Postgres by the
  contract suites.
