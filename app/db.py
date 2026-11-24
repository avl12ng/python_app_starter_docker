"""Connexion SQLAlchemy partagée par l'application, la CLI et les tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def init_engine(url: str) -> Engine:
    """Crée le moteur SQLAlchemy (appelé au démarrage de l'application)."""
    global _engine
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False, "timeout": 15}}
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    else:
        kwargs["pool_recycle"] = 1800
    _engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        event.listen(_engine, "connect", _sqlite_foreign_keys)
    SessionLocal.configure(bind=_engine)
    return _engine


def _sqlite_foreign_keys(dbapi_conn, _record) -> None:  # pragma: no cover - simples PRAGMA
    """Clés étrangères actives ; journal WAL : lectures pendant les écritures (plusieurs utilisateurs)."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Base de données non initialisée : appeler init_engine().")
    return _engine


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session SQLAlchemy par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
