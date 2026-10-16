# ADR 0002: One TTL queue per delay level instead of the delayed-message plugin

- Status: accepted
- Date: 2026-10-16

## Context

Failed messages must be retried with exponential backoff (1 s, 4 s, 16 s), then
dead-lettered. Options:

1. `rabbitmq_delayed_message_exchange` plugin.
2. One delay queue with a per-message `expiration`.
3. One queue per delay level with a queue-level `x-message-ttl`, dead-lettering
   back to the work exchange.
4. Sleep in the consumer and retry in-process.

## Decision

Option 3: `payments.new.retry.{1,2,3}` with TTLs of 1 s / 4 s / 16 s and
`x-dead-letter-exchange=payments`, `x-dead-letter-routing-key=payments.new`.
The consumer republishes a failed message to the next level (default exchange,
routing key = queue name) with `x-retry-count`, waits for the confirm, then acks.

## Consequences

- No plugin: works on any stock RabbitMQ, including managed offerings that do not
  allow plugins. The plugin also stores delayed messages in Mnesia on a single node,
  is not replicated, and is documented as unsuitable for large volumes.
- No head-of-line blocking. RabbitMQ only expires messages at the *head* of a queue,
  so in option 2 a 16 s message would hold back every 1 s message queued behind it.
  With one TTL per queue, FIFO order equals expiry order.
- Option 4 would pin a consumer slot for the whole backoff and lose the retry on a
  crash; queue-based delays survive restarts.
- One queue per level is declared up front from `MAX_RETRIES`. Changing a delay
  changes a queue argument, and RabbitMQ refuses to redeclare a queue with different
  arguments (`PRECONDITION_FAILED`): delete the retry queues when changing delays.
- Retry counting lives in our header, not in `x-death`, so the logic is explicit and
  unit-testable (`RetryPolicy`), and a garbled counter dead-letters instead of
  looping (see ADR 0005).
- TTL/DLX behaviour cannot be emulated by `TestRabbitBroker`; it is covered by
  integration tests on a real broker.
