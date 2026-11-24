"""Tests sur une base créée par les migrations Alembic (le schéma réel est testé).

Par défaut : SQLite temporaire. Pour tester sur MariaDB (comme en production), définir
TEST_DATABASE_URL=mysql+pymysql://root:root@127.0.0.1:3306/app_test?charset=utf8mb4 (base vidée à chaque test).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import Settings
from app.core import passwords
from app.db import SessionLocal
from app.main import create_app
from app.models import Role, User

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Motdepasse-Solide-42"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        secret_key="test-secret-key-0123456789abcdef0123456789",
        database_url=os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}",
        app_name="Application de test",
        login_max_failed_account=3,
        login_max_failed_per_ip_user=5,
        login_max_failed_per_ip=10,
        login_max_failed_totp=3,
        reset_max_per_ip_hour=4,
    )


@pytest.fixture
def app(settings):
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    yield create_app(settings)
    from app.db import get_engine

    get_engine().dispose()
    command.downgrade(cfg, "base")


@pytest.fixture
def client(app):
    with TestClient(app, base_url="http://testserver") as c:
        yield c


def make_user(username: str, role: str = "user", password: str = PASSWORD, **extra) -> User:
    with SessionLocal() as db:
        role_id = db.query(Role.id).filter(Role.name == role).scalar()
        user = User(
            username=username,
            email=f"{username}@exemple.fr",
            role_id=role_id,
            password_hash=passwords.hash_password(password),
            is_active=True,
            **extra,
        )
        db.add(user)
        db.commit()
        return user


@pytest.fixture
def admin(app):
    return make_user("admin", "admin")


@pytest.fixture
def basic(app):
    return make_user("alice", "user")


def csrf(client: TestClient, path: str = "/login") -> str:
    html = client.get(path).text
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match, f"jeton CSRF absent de {path}"
    return match.group(1)


def login(client: TestClient, username: str, password: str = PASSWORD, follow: bool = False):
    token = csrf(client)
    return client.post(
        "/login", data={"username": username, "password": password, "csrf": token, "next": "/"}, follow_redirects=follow
    )
