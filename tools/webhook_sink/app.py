"""Demo webhook receiver.

* ``POST /hook``  - 200, or 500 when ``WEBHOOK_SINK_FAIL=true`` (drives the DLQ demo)
* ``POST /fail``  - always 500, so e2e tests need no restart to exercise retries
* ``GET /received[?payment_id=...]`` - what arrived, including repeated deliveries
* ``DELETE /received`` - forget everything
"""

import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import FastAPI, Header, Request, Response

from outbox_payments.entrypoints.logs import configure_logging

logger = logging.getLogger("webhook_sink")


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def create_app() -> FastAPI:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    fail_hook = _flag("WEBHOOK_SINK_FAIL")
    received: list[dict[str, Any]] = []
    app = FastAPI(title="webhook-sink")

    async def record(request: Request, webhook_id: str | None, answer: int) -> Response:
        payload: dict[str, Any] = await request.json()
        received.append(
            {
                "path": request.url.path,
                "webhook_id": webhook_id,
                "payload": payload,
                "answered": answer,
                "received_at": datetime.now(UTC).isoformat(),
            }
        )
        logger.info(
            "webhook received",
            extra={
                "path": request.url.path,
                "webhook_id": webhook_id,
                "payment_id": payload.get("payment_id"),
                "status": payload.get("status"),
                "answered": answer,
            },
        )
        return Response(status_code=answer)

    @app.post("/hook")
    async def hook(  # pyright: ignore[reportUnusedFunction]
        request: Request, x_webhook_id: Annotated[str | None, Header()] = None
    ) -> Response:
        return await record(request, x_webhook_id, 500 if fail_hook else 200)

    @app.post("/fail")
    async def fail(  # pyright: ignore[reportUnusedFunction]
        request: Request, x_webhook_id: Annotated[str | None, Header()] = None
    ) -> Response:
        return await record(request, x_webhook_id, 500)

    @app.get("/received")
    async def list_received(  # pyright: ignore[reportUnusedFunction]
        payment_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            r for r in received if payment_id in (None, r["payload"].get("payment_id"))
        ]

    @app.delete("/received", status_code=204)
    async def clear() -> None:  # pyright: ignore[reportUnusedFunction]
        received.clear()

    @app.get("/health")
    async def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    return app
