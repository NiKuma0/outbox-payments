# ADR 0003: Manual dependency injection, no DI container

- Status: accepted
- Date: 2026-10-16

## Context

Use cases depend on ports (Protocols). Something has to build adapters and hand
them over, with the right lifetimes: process-wide (engine, broker, HTTP client) and
per request/message (one `AsyncSession`).

## Decision

Wire by hand in the entrypoints, using what the frameworks already provide:

- API: long-lived resources in an `ApiState` dataclass on `app.state`, created in the
  lifespan; per-request objects through FastAPI `Depends` (`get_session` ->
  `get_create_payment`).
- Consumer: a `ConsumerResources` dataclass captured by `create_broker`, injected into
  the handler with FastStream's `Depends`; the handler opens one session per message.
- Relay: plain closures in `serve()`.

## Consequences

- The whole object graph of each process is readable in one file
  (`entrypoints/api/deps.py`, `entrypoints/consumer.py`, `entrypoints/relay.py`).
- No extra dependency, no decorators on domain/application code, no container
  configuration to learn.
- Tests replace pieces with `app.dependency_overrides` (API) or by passing a different
  `ConsumerResources` (consumer). Fakes are ordinary classes.
- The cost is some repetition in the composition roots. At this size it is cheaper
  than a container; with dozens of use cases a container (e.g. `dishka`) would start
  paying for itself.
