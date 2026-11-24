"""Modèles de données de la partie authentification.

Les tables métier du moteur Python s'ajoutent ici (ou dans app/engine/models.py) puis
dans une nouvelle migration Alembic : `alembic revision --autogenerate -m "..."`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db import Base

# BIGINT sous MariaDB, INTEGER sous SQLite (seul type auto-incrémenté par SQLite)
BigId = BigInteger().with_variant(Integer, "sqlite")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")

    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )
    users: Mapped[list[User]] = relationship(back_populates="role")

    @property
    def permission_keys(self) -> set[str]:
        return {p.permission_key for p in self.permissions}


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_key", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE", onupdate="CASCADE"))
    permission_key: Mapped[str] = mapped_column(String(64))

    role: Mapped[Role] = relationship(back_populates="permissions")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(190), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT", onupdate="CASCADE"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Dernier pas de 30 s accepté : empêche de rejouer un même code TOTP
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    role: Mapped[Role] = relationship(back_populates="users", lazy="joined")

    @property
    def permissions(self) -> set[str]:
        return self.role.permission_keys if self.role else set()

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def initials(self) -> str:
        return (self.username[:2] or "?").upper()


class LoginAttempt(Base):
    """Tentatives de connexion et demandes de réinitialisation (anti force brute)."""

    __tablename__ = "auth_login_attempts"
    __table_args__ = (
        Index("idx_attempts_user", "kind", "username", "success", "attempted_at"),
        Index("idx_attempts_ip", "kind", "ip_address", "success", "attempted_at"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    # login | totp | reset_request | reset_fail
    kind: Mapped[str] = mapped_column(String(20), default="login")
    username: Mapped[str] = mapped_column(String(190), default="")
    ip_address: Mapped[str] = mapped_column(String(45))
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PasswordReset(Base):
    __tablename__ = "auth_password_resets"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    request_ip: Mapped[str] = mapped_column(String(45))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_username: Mapped[str] = mapped_column(String(50), default="", index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class WebSession(Base):
    """Session navigateur stockée côté serveur : révocable (déconnexion, compte désactivé)."""

    __tablename__ = "web_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA-256 du jeton du cookie
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    data: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
