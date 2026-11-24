"""Sessions côté serveur.

Le cookie (HttpOnly, SameSite=Lax, Secure en HTTPS) ne contient qu'un jeton aléatoire ; la base
ne stocke que son empreinte SHA-256. Une session peut donc être révoquée côté serveur
(déconnexion, compte désactivé, mot de passe réinitialisé) et expire après une période d'inactivité.
"""

from __future__ import annotations

import hashlib
import json
import random
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.clock import utcnow
from app.db import SessionLocal
from app.models import WebSession

TOUCH_EVERY = timedelta(seconds=60)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ServerSession(dict):
    """Dictionnaire qui sait s'il a été modifié et si son identifiant doit être renouvelé."""

    def __init__(self, sid: str | None = None, data: dict | None = None, last_seen=None):
        super().__init__(data or {})
        self.sid = sid
        self.last_seen = last_seen
        self.modified = False
        self.rotate_requested = False

    def __setitem__(self, key, value):
        self.modified = True
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self.modified = True
        super().__delitem__(key)

    def pop(self, key, *default):
        if key in self:
            self.modified = True
        return super().pop(key, *default)

    def clear(self):
        self.modified = True
        super().clear()

    def update(self, *args, **kwargs):
        self.modified = True
        super().update(*args, **kwargs)

    def rotate(self) -> None:
        """Nouvel identifiant de session (à la connexion) : protège contre la fixation de session."""
        self.rotate_requested = True
        self.modified = True


def _load(token: str | None, idle: timedelta) -> ServerSession:
    if not token:
        return ServerSession()
    sid = _hash(token)
    with SessionLocal() as db:
        row = db.get(WebSession, sid)
        if row is None:
            return ServerSession()
        if row.last_seen_at < utcnow() - idle:
            db.delete(row)
            db.commit()
            return ServerSession()
        try:
            data = json.loads(row.data or "{}")
        except ValueError:
            data = {}
        return ServerSession(sid=sid, data=data, last_seen=row.last_seen_at)


def _persist(session: ServerSession, idle: timedelta) -> tuple[str | None, bool]:
    """Enregistre la session. Renvoie (nouveau jeton à poser, faut-il effacer le cookie)."""
    now = utcnow()
    with SessionLocal() as db:
        if random.random() < 0.01:  # noqa: S311 - purge occasionnelle des sessions expirées
            db.execute(delete(WebSession).where(WebSession.last_seen_at < now - idle))

        if session.sid and (session.rotate_requested or not session):
            db.execute(delete(WebSession).where(WebSession.id == session.sid))
            had_cookie, session.sid = True, None
        else:
            had_cookie = False

        if not session:
            db.commit()
            return None, had_cookie

        payload = json.dumps(dict(session), default=str)
        user_id = session.get("uid")
        if session.sid:
            row = db.get(WebSession, session.sid)
            if row is not None:
                if session.modified:
                    row.data, row.user_id, row.last_seen_at = payload, user_id, now
                elif session.last_seen is None or now - session.last_seen > TOUCH_EVERY:
                    row.last_seen_at = now
                db.commit()
                return None, False

        token = secrets.token_urlsafe(32)
        db.add(WebSession(id=_hash(token), user_id=user_id, data=payload, created_at=now, last_seen_at=now))
        db.commit()
        return token, False


def revoke_user_sessions(db, user_id: int, keep_sid: str | None = None) -> None:
    """Déconnecte toutes les sessions d'un utilisateur (sauf éventuellement la session courante)."""
    stmt = delete(WebSession).where(WebSession.user_id == user_id)
    if keep_sid:
        stmt = stmt.where(WebSession.id != keep_sid)
    db.execute(stmt)


def count_user_sessions(db, user_id: int) -> int:
    return len(db.scalars(select(WebSession.id).where(WebSession.user_id == user_id)).all())


class ServerSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, cookie_name: str, idle_minutes: int, cookie_secure: str = "auto"):
        super().__init__(app)
        self.cookie_name = cookie_name
        self.idle = timedelta(minutes=idle_minutes)
        self.cookie_secure = cookie_secure

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        session = await run_in_threadpool(_load, request.cookies.get(self.cookie_name), self.idle)
        request.state.session = session
        response = await call_next(request)
        token, clear = await run_in_threadpool(_persist, session, self.idle)

        secure = request.url.scheme == "https" if self.cookie_secure == "auto" else self.cookie_secure == "true"
        if token:
            response.set_cookie(
                self.cookie_name,
                token,
                max_age=int(self.idle.total_seconds()),
                httponly=True,
                samesite="lax",
                secure=secure,
                path="/",
            )
        elif clear:
            response.delete_cookie(self.cookie_name, path="/", httponly=True, samesite="lax", secure=secure)
        return response


def get_session(request: Request) -> ServerSession:
    return request.state.session


def session_value(request: Request, key: str, default: Any = None) -> Any:
    return request.state.session.get(key, default)
