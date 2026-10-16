# ADR 0006: Test data lives apart from test logic

- Status: accepted
- Date: 2026-10-16

## Context

Most behaviour here is a table: validation rules, idempotency outcomes, webhook
status classification, retry schedule, status transitions. Written as inline
`pytest.param(...)` lists, the tables drown in test plumbing and reviewers cannot
see the business rules at a glance.

## Decision

- Test logic lives in `tests/unit|integration|e2e/` (plus `tests/contract/`).
  Test data lives in `tests/cases/`, mirroring the test tree:
  `tests/unit/domain/test_payment.py` <-> `tests/cases/domain/payment.py`.
- Case modules are **data only**: no functions, no fixtures, no I/O. Allowed values:
  literals, `Decimal`, domain enums. Each case is a `dict` typed by a `TypedDict`
  declared in the same module, so pyright strict checks the data.
- Every case has a unique kebab-case `"id"` that reads as a sentence; it becomes the
  pytest id via `tests/cases/_helpers.py::as_params`.
- Request-shaped cases use a shared base payload plus `"overrides"`.

Enforced by meta-tests in `tests/unit/test_case_modules.py`:

- ids are unique across the whole suite and kebab-case;
- case modules pass an AST purity check (no `def`/`lambda`, no calls other than
  `Decimal()`, imports only from `typing`, `decimal`, `outbox_payments.domain`,
  `tests.cases`);
- every case module has a matching test file.

## Consequences

- `pytest -v` output reads like a specification
  (`test_consumer_outcome[webhook-5xx-after-three-retries-goes-to-the-dlq]`).
- Adding a rule is adding a dict; the meta-tests stop the data modules from slowly
  turning into code.
- Application-layer enums (e.g. `WebhookVerdict`) cannot be used in cases; the cases
  use string literals typed with `Literal[...]` instead. The purity check caught this
  once during development.
- Use-case unit tests mock the persistence ports with `create_autospec` instead of
  in-memory fakes of the repositories (an earlier in-memory store was removed).
  The trade-off: those tests assert on interactions (what was passed to
  `complete_if_pending`, in what order transactions end), which is more coupled to
  the implementation than asserting on state. What the mocks take for granted is
  pinned down by the contract suites in `tests/contract`, which run on real Postgres
  (integration level); the root conftest refuses tests with no level marker.
