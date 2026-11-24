"""Commandes d'exploitation.

    python -m app.cli create-admin --username admin --email admin@exemple.fr
    python -m app.cli set-password --username admin
    python -m app.cli init-env            # crée .env depuis .env.example (secret aléatoire, base SQLite)
    python -m app.cli backup              # copie à chaud de la base SQLite (backups/app-AAAA-MM-JJ_HHMM.db)
    python -m app.cli ensure-admin        # au démarrage du conteneur, via INITIAL_ADMIN_* (facultatif, idempotent)

Le mot de passe est demandé au clavier, ou lu dans la variable ADMIN_PASSWORD.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

from app.config import get_settings
from app.core import passwords
from app.core import permissions as perms
from app.core.sessions import revoke_user_sessions
from app.db import SessionLocal, init_engine
from app.models import Role, User


def _password(env: str = "ADMIN_PASSWORD") -> str:
    pwd = os.environ.get(env) or getpass.getpass("Mot de passe : ")
    if not os.environ.get(env) and getpass.getpass("Confirmation : ") != pwd:
        sys.exit("Les deux mots de passe ne correspondent pas.")
    error = passwords.policy_error(pwd)
    if error:
        sys.exit(error)
    return pwd


def create_admin(username: str, email: str, password: str) -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).where((User.username == username) | (User.email == email))):
            sys.exit(f"Un compte « {username} » ou « {email} » existe déjà.")
        role = db.scalar(select(Role).where(Role.name == perms.SUPER_ROLE))
        if role is None:
            sys.exit("Rôle admin absent : lancez d'abord « alembic upgrade head ».")
        db.add(
            User(
                username=username,
                email=email,
                role_id=role.id,
                is_active=True,
                password_hash=passwords.hash_password(password),
            )
        )
        db.commit()
    print(f"Administrateur « {username} » créé.")


def init_env(target: Path = Path(".env"), example: Path = Path(".env.example")) -> bool:
    """Crée .env au premier lancement (SECRET_KEY aléatoire, base SQLite dans data/). Un .env existant est conservé."""
    if target.exists():
        print(f"{target} existe déjà : conservé.")
        return False
    import secrets

    db_path = (Path.cwd() / "data" / "app.db").as_posix()
    lines = []
    for line in example.read_text(encoding="utf-8").splitlines():
        if line.startswith("SECRET_KEY="):
            line = f"SECRET_KEY={secrets.token_urlsafe(48)}"
        lines.append(line)
    lines += [
        "",
        "# Base SQLite locale (sans Docker). MariaDB : mysql+pymysql://user:mdp@hote:3306/base?charset=utf8mb4",
        f"DATABASE_URL=sqlite:///{db_path}",
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{target} créé : vérifier APP_NAME, APP_SHORT, ORG_NAME, SERVER_PORT et SMTP_*.")
    return True


def backup_sqlite(url: str, output: str | None) -> Path:
    """Copie cohérente même pendant les écritures (API de sauvegarde SQLite, compatible WAL)."""
    if not url.startswith("sqlite") or "///" not in url:
        sys.exit("Base MariaDB : sauvegarder avec mariadb-dump (voir docs/technique/08-exploitation.md).")
    source = Path(url.split("///", 1)[1])
    if not source.is_file():
        sys.exit(f"Base introuvable : {source}")
    target = Path(output) if output else Path("backups") / f"app-{datetime.now():%Y-%m-%d_%H%M}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    print(f"Sauvegarde : {target}")
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="Créer un compte administrateur")
    p.add_argument("--username", required=True)
    p.add_argument("--email", required=True)
    p = sub.add_parser("set-password", help="Changer le mot de passe d'un compte (déconnecte ses sessions)")
    p.add_argument("--username", required=True)
    sub.add_parser("init-env", help="Créer .env depuis .env.example (premier lancement)")
    p = sub.add_parser("backup", help="Sauvegarder la base SQLite à chaud (application démarrée)")
    p.add_argument("--output", help="Fichier de destination (défaut : backups/app-AAAA-MM-JJ_HHMM.db)")
    sub.add_parser("ensure-admin", help="Créer l'admin INITIAL_ADMIN_* si aucun utilisateur n'existe")
    args = parser.parse_args(argv)

    if args.cmd == "init-env":
        init_env()
        return
    url = get_settings().database_url
    if args.cmd == "backup":
        backup_sqlite(url, args.output)
        return
    init_engine(url)

    if args.cmd == "create-admin":
        create_admin(args.username.strip(), args.email.strip(), _password())
    elif args.cmd == "set-password":
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == args.username))
            if user is None:
                sys.exit("Compte introuvable.")
            user.password_hash = passwords.hash_password(_password())
            revoke_user_sessions(db, user.id)
            db.commit()
        print("Mot de passe modifié.")
    elif args.cmd == "ensure-admin":
        username = os.environ.get("INITIAL_ADMIN_USERNAME", "").strip()
        email = os.environ.get("INITIAL_ADMIN_EMAIL", "").strip()
        with SessionLocal() as db:
            if db.scalar(select(func.count()).select_from(User)):
                return
        if not (username and email and os.environ.get("INITIAL_ADMIN_PASSWORD")):
            print(
                "Aucun compte : ouvrez l'application dans un navigateur pour créer l'administrateur "
                "(page « Première configuration »)."
            )
            return
        create_admin(username, email, _password("INITIAL_ADMIN_PASSWORD"))


if __name__ == "__main__":
    main()
