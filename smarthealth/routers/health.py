"""Liveness / readiness probe."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter()
log = logging.getLogger("smarthealth")


@router.get("/health")
def health(request: Request):
    """Unauthenticated; reveals nothing beyond up/down."""
    try:
        with request.app.state.session_factory() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        log.exception("health check failed")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ok"}
