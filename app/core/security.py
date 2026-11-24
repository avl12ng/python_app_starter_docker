"""En-têtes HTTP de sécurité, jeton CSRF, adresse IP du client et redirections sûres."""

from __future__ import annotations

import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

CSRF_SESSION_KEY = "csrf"
CSRF_FIELD = "csrf"
CSRF_HEADER = "X-CSRF-Token"

# Aucun script ni style en ligne dans les gabarits : la CSP peut rester stricte.
CSP = "; ".join(
    [
        "default-src 'self'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "img-src 'self' data:",
        "style-src 'self'",
        "script-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
    ]
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Content-Security-Policy", CSP)
        if request.url.scheme == "https":
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if not request.url.path.startswith("/static/"):
            # Pages authentifiées : jamais en cache (bouton Précédent après déconnexion, proxy partagé)
            h.setdefault("Cache-Control", "no-store")
        return response


class CSRFError(Exception):
    pass


def csrf_token(request: Request) -> str:
    session = request.state.session
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf(request: Request) -> None:
    request.state.session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)


async def csrf_protect(request: Request) -> None:
    """Dépendance globale : tout POST/PUT/PATCH/DELETE doit porter le jeton CSRF de la session."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.headers.get(CSRF_HEADER)
    if not sent:
        ctype = request.headers.get("content-type", "")
        if ctype.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
            form = await request.form()
            value = form.get(CSRF_FIELD)
            sent = value if isinstance(value, str) else None
    expected = request.state.session.get(CSRF_SESSION_KEY)
    if not sent or not expected or not hmac.compare_digest(str(sent), str(expected)):
        raise CSRFError()


def client_ip(request: Request) -> str:
    """IP du client. Derrière un reverse-proxy, uvicorn la corrige via --forwarded-allow-ips (voir DEPLOY)."""
    return (request.client.host if request.client else "") or "0.0.0.0"  # noqa: S104


def safe_next(target: str | None, default: str = "/") -> str:
    """N'accepte qu'un chemin local (« /admin »), jamais « //site » ni « https://site »."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return default
    return target
