import uuid

from opentelemetry import baggage, context, trace
from sqlalchemy import func, update
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.clients.db import SessionLocal
from app.models.user_sessions import UserSession
from app.telemetry.langfuse_setup import traced

COOKIE_NAME = "bandhu_sid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 14  # 14 days — matches the cleanup job's window exactly


class SessionMiddleware(BaseHTTPMiddleware):
    """Issues/validates the bandhu_sid cookie before any route runs. This is the
    anonymous identity the whole pipeline hangs a person's turns and memory off
    of — no login, no account. See backend-architecture.md §7."""

    async def dispatch(self, request: Request, call_next):
        session_id = await self._resolve_session_id(request)
        request.state.session_id = session_id

        # Stamps langfuse.session.id into OTel baggage for the rest of this
        # request's context — every @traced span downstream (langfuse_
        # setup.py) reads it back and sets it on itself, which is what lets
        # Langfuse group all of one session's traces together in its
        # Sessions view instead of showing disconnected per-request traces.
        token = context.attach(baggage.set_baggage("langfuse.session.id", str(session_id)))
        try:
            response = await call_next(request)
        finally:
            context.detach(token)

        # Deployed frontend (Netlify) and backend (Render) sit on different
        # registrable domains — every request between them is genuinely
        # cross-site, not just cross-port like local dev. SameSite=Lax
        # cookies aren't usable there at all: confirmed directly (real
        # browser context, real prod URLs) that the browser doesn't even
        # store bandhu_sid after the response, so every request minted a
        # fresh anonymous session server-side — no conversation memory, no
        # check-in history, Looking Back always empty. SameSite=None is the
        # only setting that survives a cross-site fetch, but it requires
        # Secure — browsers reject it otherwise — which local http dev can't
        # satisfy, hence the scheme-based branch below (matches this file's
        # existing secure= derivation for the same http-vs-https reason).
        is_https = request.url.scheme == "https"
        response.set_cookie(
            key=COOKIE_NAME,
            value=str(session_id),
            max_age=COOKIE_MAX_AGE,
            httponly=True,  # JS on the page can't read or tamper with it
            secure=is_https,
            samesite="none" if is_https else "lax",
        )
        return response

    @staticmethod
    @traced("session.resolve")
    async def _resolve_session_id(request: Request) -> uuid.UUID:
        span = trace.get_current_span()
        raw = request.cookies.get(COOKIE_NAME)
        candidate: uuid.UUID | None = None
        if raw:
            try:
                candidate = uuid.UUID(raw)
            except ValueError:
                candidate = None

        def resolved(session_id: uuid.UUID, *, is_new: bool) -> uuid.UUID:
            # session_id is sent raw, by deliberate choice — see the open item
            # in backend-architecture.md §10/Open Items on its 30-day Langfuse
            # retention outliving the 14-day cleanup window.
            span.set_attribute("session.id", str(session_id))
            span.set_attribute("session.is_new", is_new)
            return session_id

        if SessionLocal is None:
            # DATABASE_URL isn't configured yet — fall back to a stateless id so
            # the app is still runnable during early development, before real
            # credentials exist.
            return resolved(candidate or uuid.uuid4(), is_new=candidate is None)

        async with SessionLocal() as db:
            if candidate is not None:
                result = await db.execute(
                    update(UserSession)
                    .where(UserSession.session_id == candidate)
                    .values(last_active_at=func.now())
                )
                await db.commit()
                if result.rowcount:
                    return resolved(candidate, is_new=False)
                # Cookie present but no matching row — already cleaned up, or
                # forged. Don't trust it; fall through and issue a fresh one.

            new_id = uuid.uuid4()
            db.add(UserSession(session_id=new_id))
            await db.commit()
            return resolved(new_id, is_new=True)
