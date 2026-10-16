"""Probes. They are deliberately unauthenticated: orchestrators call them without keys."""

import asyncio
from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from outbox_payments.entrypoints.api.deps import Probe, get_readiness_probes
from outbox_payments.entrypoints.api.schemas import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> HealthResponse:
    """Liveness: the process is up. Never checks dependencies, so an outage downstream
    does not get every API replica restarted."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
async def ready(
    probes: Annotated[Mapping[str, Probe], Depends(get_readiness_probes)],
) -> JSONResponse:
    """Readiness: database and broker are reachable."""
    results = await asyncio.gather(*(probe() for probe in probes.values()))
    checks = {
        name: "ok" if healthy else "unavailable"
        for name, healthy in zip(probes, results, strict=True)
    }
    healthy = all(results)
    body = ReadinessResponse(status="ready" if healthy else "not_ready", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if healthy else 503)
