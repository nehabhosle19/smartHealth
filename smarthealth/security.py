"""Password hashing, signed tokens and login throttling (standard library only)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque


def hash_password(password: str, iterations: int) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(claims: dict, secret: str, ttl: int, now: float | None = None) -> str:
    body = dict(claims, exp=int((now if now is not None else time.time()) + ttl))
    payload = _b64(json.dumps(body, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(sig)}"


def decode_token(token: str, secret: str, now: float | None = None) -> dict | None:
    """Return the claims if the signature is valid and the token unexpired."""
    try:
        payload, sig = token.split(".")
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig)):
            return None
        claims = json.loads(_unb64(payload))
    except (ValueError, TypeError):
        return None
    if not isinstance(claims, dict) or claims.get("exp", 0) < (now if now is not None else time.time()):
        return None
    return claims


class LoginThrottle:
    """Sliding-window limiter on failed logins, keyed by username and client IP."""

    def __init__(self, max_failures: int = 5, window: int = 300):
        self.max_failures = max_failures
        self.window = window
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if not q:
            self._failures.pop(key, None)
        return q

    def blocked(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            return len(self._prune(key, now)) >= self.max_failures

    def record_failure(self, key: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._prune(key, now)
            self._failures[key].append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
