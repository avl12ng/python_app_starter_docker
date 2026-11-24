"""Dépendances FastAPI : utilisateur courant et contrôle des permissions."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User


class LoginRequired(Exception):
    """Levée quand une page exige une connexion : redirection vers /login?next=…"""


class PermissionDenied(Exception):
    """Levée quand l'utilisateur connecté n'a pas la permission : page 403."""


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Recharge l'utilisateur à chaque requête : un compte désactivé ou un rôle modifié s'applique aussitôt."""
    if hasattr(request.state, "user"):
        return request.state.user
    session = request.state.session
    uid = session.get("uid")
    user = db.get(User, uid) if uid else None
    if uid and (user is None or not user.is_active):
        session.clear()
        user = None
    request.state.user = user
    return user


def require_user(request: Request, user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def require_permission(permission: str) -> Callable[..., User]:
    def checker(user: User = Depends(require_user)) -> User:
        if not user.can(permission):
            raise PermissionDenied()
        return user

    return checker
