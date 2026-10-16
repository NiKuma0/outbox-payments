#!/usr/bin/env bash
# Walk through the main flows against a running stack (`make up` first).
set -euo pipefail

API=${API:-http://localhost:8000}
SINK=${SINK:-http://localhost:8080}
KEY=${API_KEY:-dev-api-key}
IDEMPOTENCY_KEY="demo-$(date +%s)"
BODY='{"amount": "100.00", "currency": "RUB", "description": "Order #42",
       "metadata": {"order_id": 42}, "webhook_url": "http://webhook-sink:8080/hook"}'

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
post() { curl -sS -w '\nHTTP %{http_code}\n' -X POST "$API/api/v1/payments" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" "$@"; }

step "1. Create a payment (202 Accepted)"
RESPONSE=$(post -H "Idempotency-Key: $IDEMPOTENCY_KEY" -d "$BODY")
echo "$RESPONSE"
PAYMENT_ID=$(echo "$RESPONSE" | head -n1 | python3 -c 'import json,sys; print(json.load(sys.stdin)["payment_id"])')

step "2. Repeat with the same key and body: the same payment comes back"
post -H "Idempotency-Key: $IDEMPOTENCY_KEY" -d "$BODY"

step "3. Same key, different body: 409 problem+json"
post -H "Idempotency-Key: $IDEMPOTENCY_KEY" -d "${BODY/100.00/999.00}"

step "4. Wait for the consumer (2-5 s gateway latency), then GET the payment"
sleep 7
curl -sS "$API/api/v1/payments/$PAYMENT_ID" -H "X-API-Key: $KEY"; echo

step "5. The webhook that reached webhook-sink"
curl -sS "$SINK/received?payment_id=$PAYMENT_ID"; echo

step "6. Retry/DLQ: a receiver that always answers 500"
FAILING=$(post -H "Idempotency-Key: $IDEMPOTENCY_KEY-dlq" \
  -d "${BODY/webhook-sink:8080\/hook/webhook-sink:8080/fail}" | head -n1)
echo "$FAILING"
FAILING_ID=$(echo "$FAILING" | python3 -c 'import json,sys; print(json.load(sys.stdin)["payment_id"])')
echo "Retries wait 1 s, 4 s and 16 s; give it ~30 s. Watch the queues at"
echo "  http://localhost:15672/#/queues  (guest/guest): payments.new.retry.* then payments.new.dlq"
sleep 30
echo "Deliveries seen by the sink (1 + 3 retries, same X-Webhook-Id):"
curl -sS "$SINK/received?payment_id=$FAILING_ID" | python3 -c \
  'import json,sys; [print(r["received_at"], r["webhook_id"], r["answered"]) for r in json.load(sys.stdin)]'
