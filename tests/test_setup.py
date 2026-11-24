"""Première configuration : création de l'administrateur depuis l'interface quand la base est vide."""

from __future__ import annotations

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from tests.conftest import csrf

FORM = {
    "username": "chef",
    "email": "chef@exemple.fr",
    "password": "Premier-Admin-2026",
    "password_confirm": "Premier-Admin-2026",
}


def test_base_vide_redirige_vers_la_configuration(client):
    r = client.get("/", follow_redirects=True)
    assert r.url.path == "/setup"
    assert "Créer le compte administrateur" in r.text


def test_creation_de_l_administrateur_puis_page_fermee(client):
    token = csrf(client, "/setup")
    r = client.post("/setup", data={**FORM, "csrf": token}, follow_redirects=False)
    assert r.headers["location"] == "/account#totp"
    assert client.get("/admin/users").status_code == 200  # connecté et administrateur
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "chef"))
    assert user.role.name == "admin"

    # La page n'est plus accessible, et un second envoi ne crée rien
    assert client.get("/setup", follow_redirects=False).headers["location"] == "/login"
    r = client.post(
        "/setup", data={**FORM, "username": "intrus", "email": "i@exemple.fr", "csrf": token}, follow_redirects=False
    )
    assert r.headers["location"] == "/login"
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.username == "intrus")) is None


def test_configuration_refusee_si_un_compte_existe(client, basic):
    assert client.get("/setup", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/login").status_code == 200


def test_mot_de_passe_faible_refuse(client):
    token = csrf(client, "/setup")
    r = client.post("/setup", data={**FORM, "password": "court", "password_confirm": "court", "csrf": token})
    assert r.status_code == 400 and "au moins 12 caractères" in r.text
    assert client.get("/setup", follow_redirects=False).status_code == 200  # toujours à faire


def test_sauvegarde_sqlite_a_chaud(app, settings, basic, tmp_path):
    import sqlite3

    import pytest

    if not settings.database_url.startswith("sqlite"):
        pytest.skip("sauvegarde propre à SQLite (MariaDB : mariadb-dump)")

    from app.cli import backup_sqlite

    target = backup_sqlite(settings.database_url, str(tmp_path / "copie.db"))
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT username FROM users").fetchall() == [("alice",)]


def test_init_env_cree_le_fichier_sans_ecraser(tmp_path, monkeypatch):
    from pathlib import Path

    from app.cli import init_env

    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    target, example = tmp_path / ".env", root / ".env.example"
    assert init_env(target, example) is True
    content = target.read_text(encoding="utf-8")
    assert "SECRET_KEY=change-me" not in content
    assert f"DATABASE_URL=sqlite:///{(tmp_path / 'data' / 'app.db').as_posix()}" in content
    target.write_text("SECRET_KEY=a-garder\n", encoding="utf-8")
    assert init_env(target, example) is False
    assert target.read_text(encoding="utf-8") == "SECRET_KEY=a-garder\n"
