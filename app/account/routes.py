"""Mon compte : courriel, mot de passe, double authentification (TOTP)."""

from __future__ import annotations

import time

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Form, Request
from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.config import Settings, get_settings
from app.core import audit, passwords, totp
from app.core.security import client_ip
from app.core.sessions import revoke_user_sessions
from app.db import get_db
from app.models import User
from app.web import flash, redirect, render

router = APIRouter(prefix="/account")

ENROLL_SECONDS = 600


def _log(db, request, user, action, settings, **details):
    audit.record(
        db,
        action,
        actor=user,
        target_type="user",
        target_id=user.id,
        details=details or None,
        ip=client_ip(request),
        retention_days=settings.audit_retention_days,
    )


@router.get("")
def account_page(request: Request, user: User = Depends(require_user), settings: Settings = Depends(get_settings)):
    enroll = request.state.session.get("totp_enroll")
    setup = None
    if enroll and time.time() - enroll.get("at", 0) <= ENROLL_SECONDS and not user.totp_enabled:
        uri = totp.provisioning_uri(enroll["secret"], user.username, settings.app_name)
        secret = enroll["secret"]
        setup = {
            "qr": Markup(totp.qr_svg(uri)),  # noqa: S704 - SVG généré localement par qrcode
            "secret": " ".join(secret[i : i + 4] for i in range(0, len(secret), 4)),
        }
    return render(
        request,
        "account/account.html",
        active="account",
        setup=setup,
        rules=passwords.RULES,
        min_length=passwords.MIN_LENGTH,
    )


@router.post("/email")
def change_email(
    request: Request,
    email: str = Form(""),
    current_password: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        email = validate_email(email.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        flash(request, "error", "Adresse courriel invalide.")
        return redirect("/account")
    if email.lower() == user.email.lower():
        flash(request, "info", "Le courriel est inchangé.")
        return redirect("/account")
    if not passwords.verify_password(user.password_hash, current_password):
        flash(request, "error", "Mot de passe actuel incorrect.")
        return redirect("/account")
    if db.scalar(select(User.id).where(User.email == email, User.id != user.id)):
        flash(request, "error", "Ce courriel est déjà utilisé par un autre compte.")
        return redirect("/account")
    old = user.email
    user.email = email
    _log(db, request, user, "account.email_change", settings, old=old, new=email)
    db.commit()
    flash(request, "success", "Courriel mis à jour.")
    return redirect("/account")


@router.post("/password")
def change_password(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not passwords.verify_password(user.password_hash, current_password):
        flash(request, "error", "Mot de passe actuel incorrect.")
        return redirect("/account")
    error = passwords.pair_error(new_password, new_password_confirm)
    if not error and passwords.verify_password(user.password_hash, new_password):
        error = "Le nouveau mot de passe doit être différent de l'ancien."
    if error:
        flash(request, "error", error)
        return redirect("/account")
    user.password_hash = passwords.hash_password(new_password)
    revoke_user_sessions(db, user.id, keep_sid=request.state.session.sid)
    _log(db, request, user, "account.password_change", settings)
    db.commit()
    flash(request, "success", "Mot de passe modifié. Vos autres sessions ont été déconnectées.")
    return redirect("/account")


@router.post("/totp/start")
def totp_start(request: Request, user: User = Depends(require_user)):
    if user.totp_enabled:
        flash(request, "info", "La double authentification est déjà active.")
        return redirect("/account")
    request.state.session["totp_enroll"] = {"secret": totp.generate_secret(), "at": int(time.time())}
    return redirect("/account#totp")


@router.post("/totp/confirm")
def totp_confirm(
    request: Request,
    code: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    enroll = request.state.session.get("totp_enroll")
    if not enroll or time.time() - enroll.get("at", 0) > ENROLL_SECONDS:
        request.state.session.pop("totp_enroll", None)
        flash(request, "error", "Activation expirée. Recommencez.")
        return redirect("/account")
    step = totp.verify(enroll["secret"], code)
    if step is None:
        flash(request, "error", "Code invalide. Saisissez le code à 6 chiffres affiché par l'application.")
        return redirect("/account#totp")
    user.totp_secret, user.totp_enabled, user.totp_last_step = enroll["secret"], True, step
    request.state.session.pop("totp_enroll", None)
    _log(db, request, user, "account.totp_enable", settings)
    db.commit()
    flash(request, "success", "Double authentification activée.")
    return redirect("/account")


@router.post("/totp/cancel")
def totp_cancel(request: Request, user: User = Depends(require_user)):
    request.state.session.pop("totp_enroll", None)
    return redirect("/account")


@router.post("/totp/disable")
def totp_disable(
    request: Request,
    current_password: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not passwords.verify_password(user.password_hash, current_password):
        flash(request, "error", "Mot de passe actuel incorrect.")
        return redirect("/account")
    user.totp_secret, user.totp_enabled, user.totp_last_step = None, False, None
    _log(db, request, user, "account.totp_disable", settings)
    db.commit()
    flash(request, "success", "Double authentification désactivée.")
    return redirect("/account")
