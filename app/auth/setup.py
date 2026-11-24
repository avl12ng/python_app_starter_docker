"""Première configuration : tant qu'aucun compte n'existe, /setup permet de créer l'administrateur.

Dès qu'un compte existe, la page n'est plus accessible (redirection vers la connexion).
Conseil d'exploitation : faire cette étape avant d'exposer l'application sur Internet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core import audit, passwords
from app.core import permissions as perms
from app.core import users as accounts
from app.core.security import client_ip
from app.db import get_db
from app.models import Role, User
from app.web import flash, redirect, render

router = APIRouter()


def needs_setup(request: Request, db: Session) -> bool:
    """Vrai tant que la base ne contient aucun compte (résultat mémorisé une fois la configuration faite)."""
    if getattr(request.app.state, "setup_done", False):
        return False
    if accounts.has_users(db):
        request.app.state.setup_done = True
        return False
    return True


def _page(request: Request, status_code: int = 200, **form):
    return render(
        request,
        "auth/setup.html",
        status_code=status_code,
        form=form,
        rules=passwords.RULES,
        min_length=passwords.MIN_LENGTH,
    )


@router.get("/setup")
def setup_page(request: Request, db: Session = Depends(get_db)):
    if not needs_setup(request, db):
        return redirect("/login")
    return _page(request)


@router.post("/setup")
def setup_submit(
    request: Request,
    username: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    # Verrou sur le rôle admin : deux envois simultanés ne peuvent pas créer deux administrateurs.
    role = db.scalar(select(Role).where(Role.name == perms.SUPER_ROLE).with_for_update())
    if accounts.has_users(db):
        db.rollback()
        request.app.state.setup_done = True
        flash(request, "info", "L'application est déjà configurée. Connectez-vous.")
        return redirect("/login")
    if role is None:
        db.rollback()
        flash(request, "error", "Base de données non initialisée : les migrations n'ont pas été appliquées.")
        return _page(request, status_code=500, username=username, email=email)

    username = username.strip()
    clean_email = accounts.clean_email(email)
    error = accounts.new_user_error(db, username, clean_email, password, password_confirm)
    if error:
        db.rollback()
        flash(request, "error", error)
        return _page(request, status_code=400, username=username, email=email)

    user = User(
        username=username,
        email=clean_email,
        role_id=role.id,
        is_active=True,
        password_hash=passwords.hash_password(password),
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        "user.create",
        actor=user,
        target_type="user",
        target_id=user.id,
        details={"username": username, "role": role.name, "origine": "première configuration"},
        ip=client_ip(request),
        retention_days=settings.audit_retention_days,
    )
    db.commit()
    request.app.state.setup_done = True

    from app.auth.routes import open_session  # import local : évite un import circulaire

    open_session(request, db, user, "password", settings)
    flash(request, "success", "Compte administrateur créé. Pensez à activer la double authentification.")
    return redirect("/account#totp")
