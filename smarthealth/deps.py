"""FastAPI dependencies shared by every router: DB session, authentication, authorisation."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .i18n import resolve_lang
from .models import Facility, User
from .security import decode_token

COOKIE_NAME = "sh_session"
CSRF_HEADER, CSRF_VALUE = "X-Requested-With", "smarthealth"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _token_from(request: Request) -> tuple[str | None, bool]:
    """Return (token, came_from_cookie). A Bearer header wins over the cookie."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:], False
    return request.cookies.get(COOKIE_NAME), True


def _require_csrf_header(request: Request) -> None:
    """Browsers attach cookies automatically, so cookie-authenticated writes must carry a
    header that cross-site forms cannot set."""
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(403, "Missing CSRF header")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token, via_cookie = _token_from(request)
    if via_cookie:
        _require_csrf_header(request)
    claims = decode_token(token, request.app.state.secret) if token else None
    user = db.get(User, claims["uid"]) if claims and "uid" in claims else None
    # A password change (changes `pv`) or deactivation invalidates outstanding tokens.
    if user is None or not user.is_active or claims.get("pv") != user.password_hash[-16:]:
        raise HTTPException(401, "Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"})
    return user


def admin_only(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "District administrator access required")
    return user


def facility_access(
    facility_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Facility:
    """Staff may only touch their own facility; admins may touch any."""
    if user.role != "admin" and user.facility_id != facility_id:
        raise HTTPException(403, "You may only access your own facility")
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    return facility


def lang_of(request: Request, lang: str | None = Query(None, max_length=20)) -> str:
    return resolve_lang(lang or request.headers.get("Accept-Language"))


def today_of(request: Request) -> date:
    return request.app.state.clock()
