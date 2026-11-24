"""Connexion, verrouillage, CSRF, sessions, double authentification, mot de passe oublié."""

from __future__ import annotations

import re

import pyotp
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, User, WebSession
from tests.conftest import PASSWORD, csrf, login, make_user


def test_pages_protegees_redirigent_vers_la_connexion(client):
    r = client.get("/admin/users", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=/admin/users"


def test_connexion_reussie_et_deconnexion(client, basic):
    r = login(client, "alice")
    assert r.status_code == 303 and r.headers["location"] == "/"
    home = client.get("/")
    assert home.status_code == 200 and "Bonjour alice" in home.text
    token = csrf(client, "/")
    client.post("/logout", data={"csrf": token})
    assert client.get("/", follow_redirects=False).status_code == 303
    with SessionLocal() as db:
        actions = db.scalars(select(AuditLog.action).order_by(AuditLog.id)).all()
    assert actions == ["auth.login", "auth.logout"]


def test_identifiants_invalides(client, basic):
    r = login(client, "alice", "mauvais-mot-de-passe")
    assert r.status_code == 401
    assert "Identifiant ou mot de passe incorrect" in r.text
    r = login(client, "inconnu", "peu importe")
    assert "Identifiant ou mot de passe incorrect" in r.text  # même message : pas d'énumération


def test_verrouillage_apres_trop_d_echecs(client, basic):
    for _ in range(3):
        login(client, "alice", "faux")
    r = login(client, "alice")  # bon mot de passe, mais compte verrouillé
    assert r.status_code == 401
    assert "Trop de tentatives sur ce compte" in r.text


def test_post_sans_csrf_refuse(client, basic):
    client.get("/login")
    r = client.post("/login", data={"username": "alice", "password": PASSWORD}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303  # toujours déconnecté


def test_redirection_externe_refusee(client, basic):
    token = csrf(client)
    r = client.post(
        "/login",
        data={"username": "alice", "password": PASSWORD, "csrf": token, "next": "//evil.example/"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/"


def test_identifiant_de_session_renouvele_a_la_connexion(client, basic):
    client.get("/login")
    before = client.cookies.get("app_session")
    login(client, "alice")
    after = client.cookies.get("app_session")
    assert before and after and before != after


def test_compte_desactive_deconnecte_immediatement(client, basic):
    login(client, "alice")
    with SessionLocal() as db:
        db.get(User, basic.id).is_active = False
        db.commit()
    assert client.get("/", follow_redirects=False).status_code == 303


def test_en_tetes_de_securite(client):
    r = client.get("/login")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_double_authentification(client):
    secret = pyotp.random_base32()
    make_user("bob", totp_secret=secret, totp_enabled=True)
    r = login(client, "bob")
    assert r.headers["location"] == "/login/totp"
    assert client.get("/", follow_redirects=False).status_code == 303  # pas encore connecté

    token = csrf(client, "/login/totp")
    r = client.post("/login/totp", data={"code": "000000", "csrf": token}, follow_redirects=False)
    assert r.headers["location"] == "/login/totp"

    code = pyotp.TOTP(secret).now()
    r = client.post("/login/totp", data={"code": code, "csrf": token}, follow_redirects=False)
    assert r.headers["location"] == "/"
    assert client.get("/").status_code == 200

    # Le même code ne peut pas être rejoué
    client.post("/logout", data={"csrf": csrf(client, "/")})
    login(client, "bob")
    r = client.post("/login/totp", data={"code": code, "csrf": csrf(client, "/login/totp")}, follow_redirects=False)
    assert r.headers["location"] == "/login/totp"


def test_activation_2fa_depuis_mon_compte(client, basic):
    login(client, "alice")
    client.post("/account/totp/start", data={"csrf": csrf(client, "/account")})
    page = client.get("/account").text
    assert "<svg" in page and "Code affiché par l" in page
    secret = re.search(r'class="secret">([A-Z2-7 ]+)<', page).group(1).replace(" ", "")
    client.post("/account/totp/confirm", data={"code": pyotp.TOTP(secret).now(), "csrf": csrf(client, "/account")})
    with SessionLocal() as db:
        assert db.get(User, basic.id).totp_enabled


def test_mot_de_passe_oublie(client, basic, caplog):
    token = csrf(client, "/password/forgot")
    with caplog.at_level("WARNING"):
        client.post("/password/forgot", data={"identifier": "alice", "csrf": token})
    code = re.search(r"réinitialisation pour .* : (\d{10})", caplog.text).group(1)

    token = csrf(client, "/password/reset")
    r = client.post(
        "/password/reset",
        data={
            "identifier": "alice",
            "code": "1234567890",
            "new_password": "Nouveau-Secret-2026",
            "new_password_confirm": "Nouveau-Secret-2026",
            "csrf": token,
        },
        follow_redirects=False,
    )
    assert r.status_code == 400

    r = client.post(
        "/password/reset",
        data={
            "identifier": "alice",
            "code": code,
            "new_password": "Nouveau-Secret-2026",
            "new_password_confirm": "Nouveau-Secret-2026",
            "csrf": token,
        },
        follow_redirects=False,
    )
    assert r.headers["location"] == "/login"
    assert login(client, "alice", "Nouveau-Secret-2026").headers["location"] == "/"


def test_mot_de_passe_oublie_compte_inconnu_meme_message(client):
    token = csrf(client, "/password/forgot")
    r = client.post("/password/forgot", data={"identifier": "personne", "csrf": token})
    assert "Si ce compte existe" in r.text


def test_mot_de_passe_oublie_limite_par_ip(client, basic):
    for _ in range(4):
        client.post("/password/forgot", data={"identifier": "x", "csrf": csrf(client, "/password/forgot")})
    r = client.post("/password/forgot", data={"identifier": "x", "csrf": csrf(client, "/password/forgot")})
    assert "Trop de demandes" in r.text


def test_changement_de_mot_de_passe_revoque_les_autres_sessions(app, client, basic):
    from fastapi.testclient import TestClient

    other = TestClient(app)
    login(other, "alice")
    login(client, "alice")
    client.post(
        "/account/password",
        data={
            "current_password": PASSWORD,
            "new_password": "Encore-Plus-Solide-9",
            "new_password_confirm": "Encore-Plus-Solide-9",
            "csrf": csrf(client, "/account"),
        },
    )
    assert client.get("/").status_code == 200
    assert other.get("/", follow_redirects=False).status_code == 303
    with SessionLocal() as db:
        assert len(db.scalars(select(WebSession).where(WebSession.user_id == basic.id)).all()) == 1
