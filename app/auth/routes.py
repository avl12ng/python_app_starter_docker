"""Écrans publics : connexion, double authentification, déconnexion, mot de passe oublié."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.deps import current_user
from app.auth.setup import needs_setup
from app.config import Settings, get_settings
from app.core import audit, passwords
from app.core.clock import utcnow
from app.core.mailer import send_mail
from app.core.security import client_ip, rotate_csrf, safe_next
from app.core.sessions import revoke_user_sessions
from app.db import get_db
from app.models import User
from app.web import flash, redirect, render

router = APIRouter()

TOTP_CHALLENGE_SECONDS = 300


def open_session(request: Request, db: Session, user: User, method: str, settings: Settings) -> None:
    session = request.state.session
    session.rotate()
    session.clear()
    session["uid"] = user.id
    rotate_csrf(request)
    # Connexion précédente, affichée sur l'accueil (repère en cas d'usage frauduleux du compte)
    session["prev_login"] = user.last_login_at.isoformat() if user.last_login_at else None
    user.last_login_at = utcnow()
    audit.record(
        db,
        "auth.login",
        actor=user,
        target_type="user",
        target_id=user.id,
        details={"méthode": "mot de passe" if method == "password" else "double authentification"},
        ip=client_ip(request),
        retention_days=settings.audit_retention_days,
    )
    db.commit()


@router.get("/login")
def login_page(
    request: Request, next: str = "/", user: User | None = Depends(current_user), db: Session = Depends(get_db)
):
    if user:
        return redirect(safe_next(next))
    if needs_setup(request, db):
        return redirect("/setup")
    return render(request, "auth/login.html", next=safe_next(next))


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    ip = client_ip(request)
    result = service.authenticate(db, settings, username, password, ip)
    target = safe_next(next)
    if result.error or result.user is None:
        audit.record(
            db,
            "auth.login_failed",
            actor_username=username.strip()[:50],
            ip=ip,
            retention_days=settings.audit_retention_days,
        )
        db.commit()
        flash(request, "error", result.error or "Connexion impossible.")
        return render(request, "auth/login.html", status_code=401, next=target, username=username)

    if result.needs_totp:
        session = request.state.session
        session.rotate()
        session.clear()
        session["totp_challenge"] = {"uid": result.user.id, "at": int(time.time()), "next": target}
        return redirect("/login/totp")

    open_session(request, db, result.user, "password", settings)
    return redirect(target)


def _challenge_user(request: Request, db: Session) -> User | None:
    challenge = request.state.session.get("totp_challenge")
    if not challenge or time.time() - challenge.get("at", 0) > TOTP_CHALLENGE_SECONDS:
        request.state.session.pop("totp_challenge", None)
        return None
    user = db.get(User, challenge.get("uid"))
    return user if user and user.is_active and user.totp_enabled else None


@router.get("/login/totp")
def totp_page(request: Request, db: Session = Depends(get_db)):
    user = _challenge_user(request, db)
    if user is None:
        flash(request, "error", "Session de vérification expirée. Reconnectez-vous.")
        return redirect("/login")
    return render(request, "auth/totp.html", username=user.username)


@router.post("/login/totp")
def totp_submit(
    request: Request,
    code: str = Form(""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user = _challenge_user(request, db)
    if user is None:
        flash(request, "error", "Session de vérification expirée. Reconnectez-vous.")
        return redirect("/login")
    ok, error = service.verify_totp_login(db, settings, user, code, client_ip(request))
    if not ok:
        if error:  # verrouillage : retour à l'écran de connexion
            request.state.session.pop("totp_challenge", None)
            flash(request, "error", error)
            return redirect("/login")
        flash(request, "error", "Code invalide. Vérifiez l'heure de votre téléphone et réessayez.")
        return redirect("/login/totp")
    target = request.state.session["totp_challenge"].get("next", "/")
    open_session(request, db, user, "totp", settings)
    return redirect(safe_next(target))


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    if user:
        audit.record(
            db,
            "auth.logout",
            actor=user,
            target_type="user",
            target_id=user.id,
            ip=client_ip(request),
            retention_days=settings.audit_retention_days,
        )
        db.commit()
    session = request.state.session
    session.rotate()
    session.clear()
    flash(request, "success", "Vous êtes déconnecté.")
    return redirect("/login")


# --------------------------------------------------------------------------- mot de passe oublié


@router.get("/password/forgot")
def forgot_page(request: Request):
    return render(request, "auth/forgot.html")


@router.post("/password/forgot")
def forgot_submit(
    request: Request,
    identifier: str = Form(""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    ip = client_ip(request)
    if not identifier.strip():
        flash(request, "error", "Saisissez votre identifiant ou votre courriel.")
        return redirect("/password/forgot")
    if service.reset_rate_limited(db, settings, ip):
        flash(request, "error", "Trop de demandes depuis votre poste. Réessayez dans une heure.")
        return redirect("/password/forgot")

    service.log_attempt(db, "reset_request", identifier, ip, True)
    user = service.find_by_identifier(db, identifier)
    if user and user.is_active:
        code = service.create_reset_code(db, settings, user, ip)
        body = (
            f"Bonjour {user.username},\n\n"
            f"Voici votre code de réinitialisation pour {settings.app_name} : {code}\n"
            f"Il est valable {settings.reset_ttl_minutes} minutes.\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : "
            "votre mot de passe reste inchangé."
        )
        if not send_mail(settings, user.email, f"{settings.app_name} — code de réinitialisation", body):
            db.rollback()
            flash(request, "error", "L'e-mail n'a pas pu être envoyé. Contactez un administrateur.")
            return redirect("/password/forgot")
        audit.record(
            db,
            "auth.password_reset_request",
            actor=user,
            target_type="user",
            target_id=user.id,
            ip=ip,
            retention_days=settings.audit_retention_days,
        )
    db.commit()
    # Message identique que le compte existe ou non (pas d'énumération des comptes)
    flash(
        request,
        "info",
        f"Si ce compte existe, un code à 10 chiffres vient d'être envoyé par courriel. "
        f"Il est valable {settings.reset_ttl_minutes} minutes.",
    )
    request.state.session["reset_identifier"] = identifier.strip()
    return redirect("/password/reset")


@router.get("/password/reset")
def reset_page(request: Request):
    return render(
        request,
        "auth/reset.html",
        identifier=request.state.session.get("reset_identifier", ""),
        rules=passwords.RULES,
        min_length=passwords.MIN_LENGTH,
    )


@router.post("/password/reset")
def reset_submit(
    request: Request,
    identifier: str = Form(""),
    code: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    ip = client_ip(request)
    if service.reset_rate_limited(db, settings, ip):
        flash(request, "error", "Trop de tentatives depuis votre poste. Réessayez dans une heure.")
        return redirect("/password/reset")
    user, error = service.complete_reset(db, settings, identifier, code, new_password, new_password_confirm, ip)
    if error or user is None:
        flash(request, "error", error or "Réinitialisation impossible.")
        return render(
            request,
            "auth/reset.html",
            status_code=400,
            identifier=identifier,
            rules=passwords.RULES,
            min_length=passwords.MIN_LENGTH,
        )
    revoke_user_sessions(db, user.id)
    audit.record(
        db,
        "auth.password_reset",
        actor=user,
        target_type="user",
        target_id=user.id,
        ip=ip,
        retention_days=settings.audit_retention_days,
    )
    db.commit()
    request.state.session.pop("reset_identifier", None)
    flash(request, "success", "Mot de passe modifié. Vous pouvez vous connecter.")
    return redirect("/login")
