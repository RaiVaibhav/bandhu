from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

# Both starting guesses, not validated against real traffic — same posture
# as everywhere else in this codebase (backend-architecture.md §14/§8).
# Per-session is generous for a real conversation, tight for a script;
# per-IP is a looser backstop against cookie-discarding abuse.
PER_SESSION_LIMIT = "20/10minutes"
PER_IP_LIMIT = "200/10minutes"


def rate_limit_key(request: Request) -> str:
    """Session-scoped once the bandhu_sid cookie exists; falls back to IP
    for the very first request before SessionMiddleware has issued one —
    see backend-architecture.md §8. Two layers because they catch
    different abuse shapes: a per-session cap alone doesn't stop someone
    from discarding the cookie and starting over with a fresh session on
    every request."""
    return request.cookies.get("bandhu_sid") or get_remote_address(request)


limiter = Limiter(key_func=rate_limit_key)
