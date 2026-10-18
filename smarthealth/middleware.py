"""Request guards and security response headers."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import config

SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data:; base-uri 'none'; "
                                "form-action 'self'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}
HSTS = "max-age=31536000; includeSubDomains"


def _body_too_large(request: Request) -> bool:
    try:
        return int(request.headers.get("content-length", "0")) > config.MAX_BODY_BYTES
    except ValueError:
        return True  # malformed length header


def install(app: FastAPI) -> None:
    """Attach host validation, the body-size limit and security headers."""
    if config.ALLOWED_HOSTS:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)

    @app.middleware("http")
    async def guards_and_headers(request: Request, call_next):
        if _body_too_large(request):
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if config.COOKIE_SECURE:
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        # API responses hold private data; static assets only need revalidation.
        cache = "no-store" if request.url.path.startswith("/api") else "no-cache"
        response.headers.setdefault("Cache-Control", cache)
        return response
