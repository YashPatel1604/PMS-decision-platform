"""Auth gate middleware — require a valid session when auth is enabled."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pms_platform.auth.service import get_user_by_id
from pms_platform.auth.session import SESSION_COOKIE, read_session_user_id
from pms_platform.config import settings
from pms_platform.db.base import get_session_factory

_CLIENT_PREFIXES = (
    "/strategy/pivot",
    "/strategy/charts",
    "/strategy/client-portfolio",
    "/market-data/block-deals",
    "/market-data/bulk-deals",
    "/market-data/sast",
    "/market-data/insider-trading",
)


def _is_public(path: str, method: str) -> bool:
    if method == "OPTIONS":
        return True
    if path == "/health" or path.startswith("/health/"):
        return True
    if path == "/auth/login" and method == "POST":
        return True
    if path == "/auth/me" and method == "GET":
        return True
    # OpenAPI helpers stay available for local debugging
    if path in {"/docs", "/openapi.json", "/redoc"} or path.startswith("/docs/"):
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests when AUTH_DISABLED is off."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if settings.auth_disabled or _is_public(request.url.path, request.method):
            return await call_next(request)

        if not settings.auth_secret.strip():
            return JSONResponse(
                status_code=503,
                content={"detail": "AUTH_SECRET is not configured"},
            )

        token = request.cookies.get(SESSION_COOKIE)
        user_id = read_session_user_id(token) if token else None
        if user_id is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

        session = get_session_factory()()
        try:
            user = get_user_by_id(session, user_id)
            if user is None or not user.is_active:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )
            request.state.user = user
            if user.role == "client":
                path = request.url.path
                if not (
                    path.startswith("/auth/")
                    or any(path.startswith(prefix) for prefix in _CLIENT_PREFIXES)
                ):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "This account can only use Client and Market pages."},
                    )
        finally:
            session.close()

        return await call_next(request)
