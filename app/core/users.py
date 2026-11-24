"""Validation commune à la création d'un compte (administration et première configuration)."""

from __future__ import annotations

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import passwords
from app.models import User


def clean_email(raw: str) -> str | None:
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        return None


def new_user_error(db: Session, username: str, email: str | None, password: str, confirm: str) -> str | None:
    """Message d'erreur si le compte ne peut pas être créé, sinon None. `email` doit être passé par clean_email."""
    if not username or len(username) > 50 or not username.replace(".", "").replace("-", "").replace("_", "").isalnum():
        return "Identifiant invalide (lettres, chiffres, point, tiret ou soulignement ; 50 caractères maximum)."
    if email is None:
        return "Adresse courriel invalide."
    if db.scalar(select(User.id).where(User.username == username)):
        return "Cet identifiant existe déjà."
    if db.scalar(select(User.id).where(User.email == email)):
        return "Ce courriel est déjà utilisé."
    return passwords.pair_error(password, confirm)


def has_users(db: Session) -> bool:
    return bool(db.scalar(select(func.count()).select_from(User)))
