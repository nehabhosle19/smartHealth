"""Login / logout."""
from __future__ import annotations

import functools
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, schemas
from ..deps import COOKIE_NAME, client_ip, get_db
from ..models import User
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth")
audit = logging.getLogger("smarthealth.audit")


@functools.cache
def _dummy_hash() -> str:
    """Verified for unknown usernames so login timing does not reveal which usernames exist."""
    return hash_password("dummy-password", config.PBKDF2_ITERATIONS)


def _authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    password_ok = verify_password(password, user.password_hash if user else _dummy_hash())
    return user if user and password_ok and user.is_active else None


@router.post("/login")
def login(body: schemas.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    state, ip = request.app.state, client_ip(request)
    user_key, ip_key = f"u:{body.username.lower()}", f"ip:{ip}"
    if state.user_throttle.blocked(user_key) or state.ip_throttle.blocked(ip_key):
        audit.warning("login throttled user=%s ip=%s", body.username, ip)
        raise HTTPException(429, "Too many failed attempts; try again later")

    user = _authenticate(db, body.username, body.password)
    if user is None:
        state.user_throttle.record_failure(user_key)
        state.ip_throttle.record_failure(ip_key)
        audit.warning("login failed user=%s ip=%s", body.username, ip)
        raise HTTPException(401, "Invalid username or password")

    state.user_throttle.reset(user_key)
    audit.info("login ok user=%s role=%s ip=%s", user.username, user.role, ip)
    token = create_token({"uid": user.id, "pv": user.password_hash[-16:]},
                         state.secret, config.TOKEN_TTL_SECONDS)
    # Browsers authenticate via this HttpOnly cookie (invisible to JS, so XSS cannot steal it).
    # The token is also returned for non-browser API clients.
    response.set_cookie(COOKIE_NAME, token, max_age=config.TOKEN_TTL_SECONDS, httponly=True,
                        secure=config.COOKIE_SECURE, samesite="strict", path="/api")
    return {"token": token, "role": user.role, "facility_id": user.facility_id,
            "username": user.username}


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/api")
