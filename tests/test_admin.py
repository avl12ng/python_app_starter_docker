"""Permissions, administration des utilisateurs et des rôles, journal d'audit, exports, moteur."""

from __future__ import annotations

from sqlalchemy import select

from app.db import SessionLocal
from app.engine.core import EngineError, EngineInput, parse_values, run
from app.models import Role, User
from tests.conftest import csrf, login


def test_utilisateur_simple_sans_acces_admin(client, basic):
    login(client, "alice")
    assert client.get("/admin/users").status_code == 403
    assert client.get("/engine").status_code == 200
    assert "Utilisateurs" not in client.get("/").text.split("shell__content")[0]  # pas dans le menu


def test_creation_et_modification_d_utilisateur(client, admin):
    login(client, "admin")
    token = csrf(client, "/admin/users/new")
    with SessionLocal() as db:
        role_id = db.scalar(select(Role.id).where(Role.name == "user"))
    r = client.post(
        "/admin/users/new",
        data={
            "username": "carole",
            "email": "carole@exemple.fr",
            "role_id": role_id,
            "is_active": "true",
            "password": "Bienvenue-Carole-1",
            "password_confirm": "Bienvenue-Carole-1",
            "csrf": token,
        },
        follow_redirects=False,
    )
    assert r.headers["location"] == "/admin/users"
    with SessionLocal() as db:
        carole = db.scalar(select(User).where(User.username == "carole"))
    assert carole and carole.is_active

    r = client.post(
        f"/admin/users/{carole.id}",
        data={"email": "carole@exemple.fr", "role_id": role_id, "csrf": token},
        follow_redirects=False,
    )
    with SessionLocal() as db:
        assert db.get(User, carole.id).is_active is False


def test_mot_de_passe_faible_refuse(client, admin):
    login(client, "admin")
    r = client.post(
        "/admin/users/new",
        data={
            "username": "dan",
            "email": "dan@exemple.fr",
            "role_id": 3,
            "password": "court",
            "password_confirm": "court",
            "csrf": csrf(client, "/admin/users/new"),
        },
    )
    assert r.status_code == 400 and "au moins 12 caractères" in r.text


def test_dernier_admin_protege(client, admin):
    login(client, "admin")
    token = csrf(client, "/admin/users")
    r = client.post(f"/admin/users/{admin.id}/delete", data={"csrf": token}, follow_redirects=True)
    assert "votre propre compte" in r.text
    with SessionLocal() as db:
        assert db.get(User, admin.id) is not None


def test_recherche_dynamique_et_exports(client, admin, basic):
    login(client, "admin")
    r = client.get("/admin/users?q=ali")
    assert "alice@exemple.fr" in r.text and "admin@exemple.fr" not in r.text
    csv = client.get("/admin/users/export.csv?q=ali")
    assert csv.content.startswith(b"\xef\xbb\xbf") and b"Identifiant;Courriel" in csv.content
    xlsx = client.get("/admin/users/export.xlsx")
    assert xlsx.content[:2] == b"PK"


def test_permissions_du_role_admin_verrouillees(client, admin):
    login(client, "admin")
    client.post("/admin/roles", data={"csrf": csrf(client, "/admin/roles")})  # tout décoché
    with SessionLocal() as db:
        keys = db.scalar(select(Role).where(Role.name == "admin")).permission_keys
    assert {"admin.access", "users.manage", "roles.manage"} <= keys
    assert client.get("/admin/users").status_code == 200


def test_journal_d_audit(client, admin):
    login(client, "admin")
    r = client.get("/admin/audit?q=admin")
    assert r.status_code == 200 and "Connexion" in r.text
    assert client.get("/admin/audit/export.csv").status_code == 200


def test_moteur_page_et_api(client, basic):
    login(client, "alice")
    r = client.post("/engine", data={"label": "Lot", "values": "1 ; 2,5 ; 4", "csrf": csrf(client, "/engine")})
    assert r.status_code == 200 and "2,5" in r.text
    assert ">1 ; 2,5 ; 4</textarea>" in r.text  # la saisie est conservée
    token = csrf(client, "/engine")
    r = client.post("/api/engine/run", json={"values": [1, 2, 3]}, headers={"X-CSRF-Token": token})
    assert r.json()["result"]["mean"] == 2
    assert client.post("/api/engine/run", json={"values": [1, 2]}).status_code == 403  # sans jeton CSRF


def test_moteur_seul():
    assert parse_values("1,5 2\n3") == [1.5, 2.0, 3.0]
    assert run(EngineInput([2, 4])).mean == 3
    try:
        parse_values("1 abc")
    except EngineError as exc:
        assert "abc" in str(exc)
