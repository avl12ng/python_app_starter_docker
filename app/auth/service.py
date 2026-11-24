"""Logique d'authentification : connexion, verrouillage anti force brute, TOTP, réinitialisation.

Indépendant de FastAPI : testable seul et réutilisable depuis la CLI.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.core import passwords, totp
from app.core.clock import utcnow
from app.models import LoginAttempt, PasswordReset, User

FAILURE_KINDS = ("login", "totp")


@dataclass
class LoginResult:
    user: User | None = None
    needs_totp: bool = False
    error: str | None = None


# --------------------------------------------------------------------------- tentatives


def log_attempt(db: Session, kind: str, username: str, ip: str, success: bool) -> None:
    db.add(LoginAttempt(kind=kind, username=username[:190], ip_address=ip[:45], success=success, attempted_at=utcnow()))


def _failures(
    db: Session,
    minutes: int,
    *,
    username: str | None = None,
    ip: str | None = None,
    kinds: tuple[str, ...] = FAILURE_KINDS,
):
    since = utcnow() - timedelta(minutes=minutes)
    stmt = select(func.count(), func.min(LoginAttempt.attempted_at)).where(
        LoginAttempt.success.is_(False), LoginAttempt.attempted_at > since, LoginAttempt.kind.in_(kinds)
    )
    if username:
        stmt = stmt.where(LoginAttempt.username == username)
    if ip:
        stmt = stmt.where(LoginAttempt.ip_address == ip)
    count, oldest = db.execute(stmt).one()
    remaining = minutes
    if oldest is not None:
        left = (oldest + timedelta(minutes=minutes) - utcnow()).total_seconds() / 60
        remaining = max(1, min(minutes, math.ceil(left)))
    return int(count), remaining


def lock_message(db: Session, settings: Settings, username: str, ip: str) -> str | None:
    """Message si la connexion est verrouillée (compte, couple IP + compte, ou IP), sinon None."""
    minutes = settings.login_lockout_minutes
    checks = [
        (
            {"username": username},
            settings.login_max_failed_account,
            "Trop de tentatives sur ce compte. Réessayez dans {m} min.",
        ),
        (
            {"username": username, "ip": ip},
            settings.login_max_failed_per_ip_user,
            "Trop de tentatives depuis votre poste. Réessayez dans {m} min.",
        ),
        (
            {"ip": ip},
            settings.login_max_failed_per_ip,
            "Trop de tentatives depuis votre adresse IP. Réessayez dans {m} min.",
        ),
    ]
    for filters, limit, message in checks:
        count, remaining = _failures(db, minutes, **filters)
        if count >= limit:
            return message.format(m=remaining)
    return None


# --------------------------------------------------------------------------- connexion


def authenticate(db: Session, settings: Settings, username: str, password: str, ip: str) -> LoginResult:
    username = username.strip()
    if not username or not password:
        return LoginResult(error="Saisissez votre identifiant et votre mot de passe.")

    locked = lock_message(db, settings, username, ip)
    if locked:
        log_attempt(db, "login", username, ip, False)
        db.commit()
        return LoginResult(error=locked)

    user = db.scalar(select(User).where(User.username == username))
    valid = passwords.verify_password(user.password_hash if user else None, password)
    if not user or not valid or not user.is_active:
        log_attempt(db, "login", username, ip, False)
        db.commit()
        return LoginResult(error="Identifiant ou mot de passe incorrect.")

    log_attempt(db, "login", username, ip, True)
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    db.commit()

    if user.totp_enabled and user.totp_secret:
        return LoginResult(user=user, needs_totp=True)
    return LoginResult(user=user)


def verify_totp_login(db: Session, settings: Settings, user: User, code: str, ip: str) -> tuple[bool, str | None]:
    """Deuxième étape. Renvoie (succès, message d'erreur ; None si le code est simplement faux)."""
    locked = lock_message(db, settings, user.username, ip)
    if locked:
        return False, locked
    step = totp.verify(user.totp_secret or "", code, user.totp_last_step)
    if step is None:
        log_attempt(db, "totp", user.username, ip, False)
        db.commit()
        count, remaining = _failures(db, settings.login_lockout_minutes, username=user.username)
        if count >= settings.login_max_failed_totp:
            return False, f"Trop de codes invalides. Réessayez dans {remaining} min."
        return False, None
    user.totp_last_step = step
    log_attempt(db, "totp", user.username, ip, True)
    db.commit()
    return True, None


# --------------------------------------------------------------------------- mot de passe oublié


def _reset_hash(settings: Settings, code: str, user_id: int) -> str:
    return hmac.new(settings.secret_key.encode(), f"{code}|{user_id}".encode(), hashlib.sha256).hexdigest()


def find_by_identifier(db: Session, identifier: str) -> User | None:
    identifier = identifier.strip()
    if not identifier:
        return None
    return db.scalar(select(User).where(or_(User.username == identifier, User.email == identifier)))


def reset_rate_limited(db: Session, settings: Settings, ip: str) -> bool:
    """Limite par IP et par heure les demandes de code ET les codes erronés (force brute du code)."""
    since = utcnow() - timedelta(hours=1)
    count = db.scalar(
        select(func.count()).where(
            LoginAttempt.kind.in_(("reset_request", "reset_fail")),
            LoginAttempt.ip_address == ip,
            LoginAttempt.attempted_at > since,
        )
    )
    return int(count or 0) >= settings.reset_max_per_ip_hour


def create_reset_code(db: Session, settings: Settings, user: User, ip: str) -> str:
    """Invalide les codes précédents et crée un code à 10 chiffres (renvoyé pour l'e-mail)."""
    code = str(secrets.randbelow(9_000_000_000) + 1_000_000_000)
    now = utcnow()
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .values(used_at=now)
    )
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=_reset_hash(settings, code, user.id),
            request_ip=ip,
            expires_at=now + timedelta(minutes=settings.reset_ttl_minutes),
            created_at=now,
        )
    )
    return code


def complete_reset(
    db: Session, settings: Settings, identifier: str, code: str, new: str, confirm: str, ip: str
) -> tuple[User | None, str | None]:
    code = code.strip()
    if not identifier.strip():
        return None, "Saisissez votre identifiant ou votre courriel."
    if not code.isdigit() or len(code) != 10:
        return None, "Le code doit comporter 10 chiffres."
    error = passwords.pair_error(new, confirm)
    if error:
        return None, error

    user = find_by_identifier(db, identifier)
    reset = None
    if user and user.is_active:
        expected = _reset_hash(settings, code, user.id)
        candidates = db.scalars(
            select(PasswordReset).where(
                PasswordReset.user_id == user.id,
                PasswordReset.used_at.is_(None),
                PasswordReset.expires_at > utcnow(),
            )
        ).all()
        reset = next((r for r in candidates if hmac.compare_digest(r.token_hash, expected)), None)
    if reset is None or user is None:
        log_attempt(db, "reset_fail", identifier, ip, False)
        db.commit()
        return None, "Code invalide ou expiré. Demandez un nouveau code."
    if passwords.verify_password(user.password_hash, new):
        return None, "Le nouveau mot de passe doit être différent de l'ancien."

    now = utcnow()
    user.password_hash = passwords.hash_password(new)
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .values(used_at=now)
    )
    return user, None
