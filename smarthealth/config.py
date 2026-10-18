"""Runtime configuration, read from the environment (12-factor style).

See `.env.example` for every variable. In production (SMARTHEALTH_ENV=production) the app
refuses to start with unsafe settings instead of silently falling back to insecure defaults.
"""
import os
import secrets
from datetime import date, datetime
from zoneinfo import ZoneInfo

ENV = os.getenv("SMARTHEALTH_ENV", "development").lower()
IS_PROD = ENV == "production"


def _database_url() -> str:
    url = os.getenv("SMARTHEALTH_DB") or os.getenv("DATABASE_URL") or "sqlite:///./smarthealth.db"
    # Heroku/Render style URLs -> SQLAlchemy + psycopg 3 driver
    for old in ("postgres://", "postgresql://"):
        if url.startswith(old):
            return "postgresql+psycopg://" + url[len(old):]
    return url


DATABASE_URL = _database_url()
# A random per-process key is only acceptable for development (tokens die on restart).
SECRET_KEY = os.getenv("SMARTHEALTH_SECRET") or secrets.token_hex(32)
SECRET_FROM_ENV = bool(os.getenv("SMARTHEALTH_SECRET"))
TOKEN_TTL_SECONDS = int(os.getenv("SMARTHEALTH_TOKEN_TTL", str(8 * 3600)))
PBKDF2_ITERATIONS = int(os.getenv("SMARTHEALTH_PBKDF2_ITERS", "600000"))  # OWASP 2023 minimum
COOKIE_SECURE = os.getenv("SMARTHEALTH_COOKIE_SECURE", "true" if IS_PROD else "false").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("SMARTHEALTH_ALLOWED_HOSTS", "").split(",") if h.strip()]
TIMEZONE = os.getenv("SMARTHEALTH_TZ", "Asia/Kolkata")
LOG_LEVEL = os.getenv("SMARTHEALTH_LOG_LEVEL", "INFO").upper()
MAX_BODY_BYTES = 64 * 1024
MIN_PASSWORD_LENGTH = 12

# Analytics tunables
HISTORY_DAYS = 28          # consumption history used for forecasting
FORECAST_HORIZON = 14      # days of demand forecast
LEAD_TIME_DAYS = 7         # replenishment lead time -> warning threshold
CRITICAL_COVER_DAYS = 3    # cover below this is critical
TARGET_COVER_DAYS = 14     # cover a deficit facility is topped up to
DONOR_MIN_COVER_DAYS = 30  # only facilities above this may donate
DONOR_RESERVE_DAYS = 21    # cover a donor always keeps
FLAG_THRESHOLD = 40        # facility risk score at which admins are alerted
HIGH_SEVERITY_THRESHOLD = 65
STALE_DATA_DAYS = 3


def local_today() -> date:
    """Today's date in the deployment timezone (containers default to UTC, India is UTC+5:30)."""
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def production_problems(secret: str, secret_from_env: bool, cookie_secure: bool) -> list[str]:
    """Return a list of reasons the configuration is unsafe for production (empty if fine)."""
    problems = []
    if not secret_from_env or len(secret) < 32:
        problems.append("SMARTHEALTH_SECRET must be set to a random value of at least 32 characters "
                        "(generate one with: python -c \"import secrets; print(secrets.token_hex(32))\")")
    if not cookie_secure:
        problems.append("SMARTHEALTH_COOKIE_SECURE must be true in production (serve over HTTPS)")
    return problems
