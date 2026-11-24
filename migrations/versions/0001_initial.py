"""Schéma initial : rôles, permissions, utilisateurs, tentatives, réinitialisations, audit, sessions.

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BigId = sa.BigInteger().with_variant(sa.Integer, "sqlite")
MYSQL = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}

ROLES = [
    (1, "admin", "Administrateur"),
    (2, "manager", "Responsable"),
    (3, "user", "Utilisateur"),
]
ROLE_PERMISSIONS = {
    1: ["admin.access", "users.manage", "roles.manage", "audit.view", "engine.run"],
    2: ["audit.view", "engine.run"],
    3: ["engine.run"],
}


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        **MYSQL,
    )
    role_permissions = op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "role_id", sa.Integer, sa.ForeignKey("roles.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
        ),
        sa.Column("permission_key", sa.String(64), nullable=False),
        sa.UniqueConstraint("role_id", "permission_key", name="uq_role_permission"),
        **MYSQL,
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("email", sa.String(190), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role_id",
            sa.Integer,
            sa.ForeignKey("roles.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("totp_secret", sa.String(64), nullable=True),
        sa.Column("totp_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("totp_last_step", sa.BigInteger, nullable=True),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        **MYSQL,
    )
    op.create_table(
        "auth_login_attempts",
        sa.Column("id", BigId, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="login"),
        sa.Column("username", sa.String(190), nullable=False, server_default=""),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("attempted_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        **MYSQL,
    )
    op.create_index("idx_attempts_user", "auth_login_attempts", ["kind", "username", "success", "attempted_at"])
    op.create_index("idx_attempts_ip", "auth_login_attempts", ["kind", "ip_address", "success", "attempted_at"])
    op.create_table(
        "auth_password_resets",
        sa.Column("id", BigId, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, index=True),
        sa.Column("request_ip", sa.String(45), nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("used_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        **MYSQL,
    )
    op.create_table(
        "audit_log",
        sa.Column("id", BigId, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("actor_username", sa.String(50), nullable=False, server_default="", index=True),
        sa.Column("action", sa.String(80), nullable=False, index=True),
        sa.Column("target_type", sa.String(40), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        **MYSQL,
    )
    op.create_table(
        "web_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=True, index=True),
        sa.Column("data", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        **MYSQL,
    )

    op.bulk_insert(roles, [{"id": i, "name": n, "description": d} for i, n, d in ROLES])
    op.bulk_insert(
        role_permissions,
        [{"role_id": rid, "permission_key": key} for rid, keys in ROLE_PERMISSIONS.items() for key in keys],
    )


def downgrade() -> None:
    for table in (
        "web_sessions",
        "audit_log",
        "auth_password_resets",
        "auth_login_attempts",
        "users",
        "role_permissions",
        "roles",
    ):
        op.drop_table(table)
