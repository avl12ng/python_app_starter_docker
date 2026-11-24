"""Hachage Argon2id et politique de mot de passe (mêmes règles que secure_website_starter)."""

from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 12

_hasher = PasswordHasher()
# Hash factice : la vérification d'un compte inexistant prend le même temps qu'un vrai compte.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

RULES: list[tuple[str, str]] = [
    ("length", f"Au moins {MIN_LENGTH} caractères"),
    ("upper", "Une lettre majuscule"),
    ("lower", "Une lettre minuscule"),
    ("digit", "Un chiffre"),
    ("special", "Un caractère spécial"),
]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def policy_error(password: str) -> str | None:
    """Message d'erreur si le mot de passe ne respecte pas la politique, sinon None."""
    if len(password) < MIN_LENGTH:
        return f"Le mot de passe doit contenir au moins {MIN_LENGTH} caractères."
    checks = [r"[A-Z]", r"[a-z]", r"[0-9]", r"[^A-Za-z0-9]"]
    if not all(re.search(p, password) for p in checks):
        return "Le mot de passe doit contenir une majuscule, une minuscule, un chiffre et un caractère spécial."
    return None


def pair_error(password: str, confirm: str) -> str | None:
    if not password or not confirm:
        return "Saisissez le mot de passe et sa confirmation."
    if password != confirm:
        return "Les deux mots de passe ne correspondent pas."
    return policy_error(password)
