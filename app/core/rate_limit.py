"""Rate limiting using slowapi (must decorate routes; app.state.limiter alone is not enough)."""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import RATE_LIMIT_ENABLED, RATE_LIMIT_PER_MINUTE

limiter = Limiter(key_func=get_remote_address)

# Strict limits for credential endpoints (brute-force protection)
AUTH_RATE_LIMIT = "5/minute"


def get_rate_limit_string() -> str:
    """Default global rate limit string for slowapi."""
    if RATE_LIMIT_ENABLED:
        return f"{RATE_LIMIT_PER_MINUTE}/minute"
    return "1000/minute"


def auth_rate_limit() -> str:
    """Limit for login / token. Disabled only when RATE_LIMIT_ENABLED=false."""
    if RATE_LIMIT_ENABLED:
        return AUTH_RATE_LIMIT
    return "1000/minute"


def setup_rate_limiting(app):
    """Attach limiter to the app so @limiter.limit decorators work."""
    app.state.limiter = limiter
    if RATE_LIMIT_ENABLED:
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return app
