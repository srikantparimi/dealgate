import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from app.routers import (
    actuals,
    admin_bulk_imports,
    admin_function_owners,
    admin_policy,
    admin_rate_cards,
    admin_replay,
    admin_users,
    adviser,
    agreements,
    approvals,
    audit,
    capability_catalog,
    ceo_exception,
    client_rate_cards,
    clients,
    dashboards,
    deals,
    delivery_model,
    forecast,
    gm,
    health,
    hubspot,
    legacy,
    me,
    notifications,
    renewals,
    signatories,
    signed_sow,
    sow,
    sows_staffing,
    sows_upload,
    tasks,
)

log = logging.getLogger("dealgate.api")

app = FastAPI(title="DealGate API", version="0.0.1")


def _debug_detail() -> bool:
    """Include the exception text in the response body outside production."""

    return os.environ.get("DEALGATE_ENV", "local") in ("local", "test", "dev")


@app.exception_handler(ProgrammingError)
@app.exception_handler(OperationalError)
async def _schema_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A database schema or connectivity fault.

    This is the class of failure that produced "API error 500" with no
    explanation: a migration had not been applied, so the first query in the
    handler raised and Starlette returned a bare plain-text body with no JSON
    `detail` for the browser to show. 503 is the honest code — the service
    cannot serve the request, and it is not the caller's fault.
    """

    correlation_id = str(uuid.uuid4())
    log.exception(
        "database error", extra={"correlation_id": correlation_id, "path": request.url.path}
    )
    detail: dict[str, object] = {
        "message": (
            "The service could not reach the database in the expected shape. "
            "This usually means a pending migration."
        ),
        "correlation_id": correlation_id,
        "error_type": type(exc).__name__,
    }
    if _debug_detail():
        detail["error"] = str(exc)
    return JSONResponse(status_code=503, content={"detail": detail})


@app.exception_handler(IntegrityError)
async def _integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    correlation_id = str(uuid.uuid4())
    log.warning(
        "integrity error",
        extra={"correlation_id": correlation_id, "path": request.url.path},
    )
    detail: dict[str, object] = {
        "message": "That change conflicts with a record that already exists.",
        "correlation_id": correlation_id,
        "error_type": "IntegrityError",
    }
    if _debug_detail():
        detail["error"] = str(exc)
    return JSONResponse(status_code=409, content={"detail": detail})


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort. Changes the envelope, never the outcome.

    A 500 is still a 500 and the full traceback is still logged — the only
    thing this removes is Starlette's bare-text body, which the browser client
    could not extract a message from. The correlation id is what ties the red
    banner a user reports to the line in CloudWatch.
    """

    correlation_id = str(uuid.uuid4())
    log.exception(
        "unhandled exception",
        extra={"correlation_id": correlation_id, "path": request.url.path},
    )
    detail: dict[str, object] = {
        "message": "Something went wrong on our side.",
        "correlation_id": correlation_id,
        "error_type": type(exc).__name__,
    }
    if _debug_detail():
        detail["error"] = str(exc)
    return JSONResponse(status_code=500, content={"detail": detail})

app.include_router(health.router)
app.include_router(me.router)
app.include_router(hubspot.router)
app.include_router(deals.router)
app.include_router(audit.router)
app.include_router(admin_users.router)
app.include_router(clients.router)
app.include_router(client_rate_cards.router)
app.include_router(agreements.router)
app.include_router(tasks.router)
app.include_router(notifications.router)
app.include_router(admin_rate_cards.router)
app.include_router(admin_policy.router)
app.include_router(gm.router)
app.include_router(sow.router)
app.include_router(sows_staffing.router)
app.include_router(sows_upload.router)
app.include_router(delivery_model.router)
app.include_router(adviser.router)
app.include_router(legacy.router)
app.include_router(approvals.router)
app.include_router(ceo_exception.router)
app.include_router(signatories.router)
app.include_router(signed_sow.router)
app.include_router(renewals.router)
app.include_router(dashboards.router)
app.include_router(forecast.router)
app.include_router(actuals.router)
app.include_router(admin_replay.router)
app.include_router(admin_function_owners.router)
app.include_router(admin_bulk_imports.router)
app.include_router(capability_catalog.router)
