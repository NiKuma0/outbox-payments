"""RFC 9457 problem details (``application/problem+json``) for every error response."""

import logging
from collections.abc import Mapping, Sequence

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from outbox_payments.application.errors import (
    IdempotencyKeyConflictError,
    PaymentNotFoundError,
)
from outbox_payments.domain import DomainError

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


class ProblemError(Exception):
    """Raise from routes or dependencies to answer with a problem document."""

    def __init__(
        self,
        status: int,
        title: str,
        *,
        detail: str | None = None,
        problem_type: str = "about:blank",
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(title)
        self.status = status
        self.title = title
        self.detail = detail
        self.problem_type = problem_type
        self.headers = dict(headers or {})


def problem_response(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str | None = None,
    problem_type: str = "about:blank",
    errors: Sequence[Mapping[str, str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, object] = {
        "type": problem_type,
        "title": title,
        "status": status,
        "instance": request.url.path,
    }
    if detail is not None:
        body["detail"] = detail
    if errors is not None:
        body["errors"] = list(errors)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def _field_name(location: Sequence[int | str]) -> str:
    # ("body", "metadata", "x") -> "metadata.x"; ("path", "payment_id") -> "payment_id"
    parts = [str(part) for part in location[1:]] or [str(location[0])]
    return ".".join(parts)


async def _on_problem(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProblemError)
    return problem_response(
        request,
        status=exc.status,
        title=exc.title,
        detail=exc.detail,
        problem_type=exc.problem_type,
        headers=exc.headers,
    )


async def _on_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"field": _field_name(error["loc"]), "message": str(error["msg"])} for error in exc.errors()
    ]
    return problem_response(
        request,
        status=422,
        title="Request validation failed",
        problem_type="/problems/validation-error",
        errors=errors,
    )


async def _on_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return problem_response(
        request, status=exc.status_code, title=str(exc.detail), headers=exc.headers
    )


async def _on_not_found(request: Request, exc: Exception) -> JSONResponse:
    return problem_response(
        request,
        status=404,
        title="Payment not found",
        detail=str(exc),
        problem_type="/problems/payment-not-found",
    )


async def _on_idempotency_conflict(request: Request, exc: Exception) -> JSONResponse:
    return problem_response(
        request,
        status=409,
        title="Idempotency key reused with a different request",
        detail=str(exc),
        problem_type="/problems/idempotency-key-conflict",
    )


async def _on_domain_error(request: Request, exc: Exception) -> JSONResponse:
    return problem_response(
        request,
        status=422,
        title="Business rule violated",
        detail=str(exc),
        problem_type="/problems/domain-error",
    )


async def _on_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled error", extra={"path": request.url.path}, exc_info=exc)
    return problem_response(request, status=500, title="Internal server error")


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProblemError, _on_problem)
    app.add_exception_handler(RequestValidationError, _on_validation_error)
    app.add_exception_handler(StarletteHTTPException, _on_http_exception)
    app.add_exception_handler(PaymentNotFoundError, _on_not_found)
    app.add_exception_handler(IdempotencyKeyConflictError, _on_idempotency_conflict)
    app.add_exception_handler(DomainError, _on_domain_error)
    app.add_exception_handler(Exception, _on_unexpected)
