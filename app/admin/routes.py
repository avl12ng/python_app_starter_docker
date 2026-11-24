"""Administration : utilisateurs, rôles et permissions, journal d'audit, à propos."""

from __future__ import annotations

import json
import platform
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app import __version__
from app.auth.deps import require_permission
from app.config import Settings, get_settings
from app.core import audit, passwords
from app.core import permissions as perms
from app.core import users as accounts
from app.core.clock import utcnow
from app.core.exports import csv_response, xlsx_response
from app.core.security import client_ip
from app.core.sessions import revoke_user_sessions
from app.db import get_db
from app.models import AuditLog, Role, RolePermission, User
from app.web import flash, redirect, render

router = APIRouter(prefix="/admin")

CHANGELOG = [
    ("0.1.0", "Squelette initial : authentification, 2FA, administration, journal d'audit, moteur d'exemple."),
]


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _words(q: str) -> list[str]:
    return [w for w in q.split() if len(w) >= 2]


def _log(db, request, actor, action, settings, target_type=None, target_id=None, **details):
    audit.record(
        db,
        action,
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        details=details or None,
        ip=client_ip(request),
        retention_days=settings.audit_retention_days,
    )


# =========================================================================== utilisateurs


def _users_query(q: str, role: str, status: str):
    stmt = select(User).join(User.role).order_by(User.username)
    for word in _words(q):
        pattern = _like(word)
        stmt = stmt.where(or_(User.username.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\")))
    if role:
        stmt = stmt.where(Role.name == role)
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(User.is_active.is_(False))
    return stmt


def _is_last_admin(db: Session, user: User) -> bool:
    if user.role.name != perms.SUPER_ROLE or not user.is_active:
        return False
    count = db.scalar(
        select(func.count())
        .select_from(User)
        .join(User.role)
        .where(Role.name == perms.SUPER_ROLE, User.is_active.is_(True))
    )
    return (count or 0) <= 1


@router.get("/users")
def users_list(
    request: Request,
    q: str = "",
    role: str = "",
    status: str = "",
    actor: User = Depends(require_permission(perms.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    users = db.scalars(_users_query(q, role, status)).unique().all()
    roles = db.scalars(select(Role).order_by(Role.name)).all()
    totals = {
        "all": len(users),
        "active": sum(1 for u in users if u.is_active),
        "totp": sum(1 for u in users if u.totp_enabled),
    }
    return render(
        request,
        "admin/users.html",
        active="users",
        users=users,
        roles=roles,
        totals=totals,
        filters={"q": q, "role": role, "status": status},
        query=request.url.query,
    )


@router.get("/users/export.{fmt}")
def users_export(
    fmt: str,
    q: str = "",
    role: str = "",
    status: str = "",
    actor: User = Depends(require_permission(perms.USERS_MANAGE)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    users = db.scalars(_users_query(q, role, status)).unique().all()
    headers = ["Identifiant", "Courriel", "Rôle", "Actif", "2FA", "Dernière connexion", "Créé le"]
    rows = [
        [
            u.username,
            u.email,
            u.role.description or u.role.name,
            u.is_active,
            u.totp_enabled,
            u.last_login_at,
            u.created_at,
        ]
        for u in users
    ]
    if fmt == "xlsx":
        return xlsx_response("utilisateurs", "Utilisateurs", headers, rows, settings.timezone)
    return csv_response("utilisateurs", headers, rows, settings.timezone)


@router.get("/users/new")
def user_new(
    request: Request, actor: User = Depends(require_permission(perms.USERS_MANAGE)), db: Session = Depends(get_db)
):
    roles = db.scalars(select(Role).order_by(Role.name)).all()
    return render(
        request,
        "admin/user_form.html",
        active="users",
        target=None,
        roles=roles,
        rules=passwords.RULES,
        min_length=passwords.MIN_LENGTH,
        form={},
    )


@router.post("/users/new")
def user_create(
    request: Request,
    username: str = Form(""),
    email: str = Form(""),
    role_id: int = Form(0),
    password: str = Form(""),
    password_confirm: str = Form(""),
    is_active: bool = Form(False),
    actor: User = Depends(require_permission(perms.USERS_MANAGE)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    username = username.strip()
    clean_email = accounts.clean_email(email)
    role = db.get(Role, role_id)
    error = "Choisissez un rôle." if role is None else None
    error = error or accounts.new_user_error(db, username, clean_email, password, password_confirm)
    if error:
        flash(request, "error", error)
        roles = db.scalars(select(Role).order_by(Role.name)).all()
        return render(
            request,
            "admin/user_form.html",
            status_code=400,
            active="users",
            target=None,
            roles=roles,
            rules=passwords.RULES,
            min_length=passwords.MIN_LENGTH,
            form={"username": username, "email": email, "role_id": role_id, "is_active": is_active},
        )
    user = User(
        username=username,
        email=clean_email,
        role_id=role.id,
        is_active=is_active,
        password_hash=passwords.hash_password(password),
    )
    db.add(user)
    db.flush()
    _log(db, request, actor, "user.create", settings, "user", user.id, username=username, role=role.name)
    db.commit()
    flash(request, "success", f"Utilisateur « {username} » créé.")
    return redirect("/admin/users")


@router.get("/users/{user_id}")
def user_edit(
    request: Request,
    user_id: int,
    actor: User = Depends(require_permission(perms.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        flash(request, "error", "Utilisateur introuvable.")
        return redirect("/admin/users")
    roles = db.scalars(select(Role).order_by(Role.name)).all()
    return render(
        request,
        "admin/user_form.html",
        active="users",
        target=target,
        roles=roles,
        rules=passwords.RULES,
        min_length=passwords.MIN_LENGTH,
        form={
            "username": target.username,
            "email": target.email,
            "role_id": target.role_id,
            "is_active": target.is_active,
        },
    )


@router.post("/users/{user_id}")
def user_update(
    request: Request,
    user_id: int,
    email: str = Form(""),
    role_id: int = Form(0),
    is_active: bool = Form(False),
    password: str = Form(""),
    password_confirm: str = Form(""),
    reset_totp: bool = Form(False),
    actor: User = Depends(require_permission(perms.USERS_MANAGE)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    target = db.get(User, user_id)
    if target is None:
        flash(request, "error", "Utilisateur introuvable.")
        return redirect("/admin/users")
    back = f"/admin/users/{user_id}"
    clean_email = accounts.clean_email(email)
    role = db.get(Role, role_id)
    if clean_email is None:
        flash(request, "error", "Adresse courriel invalide.")
        return redirect(back)
    if role is None:
        flash(request, "error", "Choisissez un rôle.")
        return redirect(back)
    if db.scalar(select(User.id).where(User.email == clean_email, User.id != target.id)):
        flash(request, "error", "Ce courriel est déjà utilisé.")
        return redirect(back)
    if target.id == actor.id and (not is_active or role.id != target.role_id):
        flash(request, "error", "Vous ne pouvez pas désactiver votre propre compte ni changer votre rôle.")
        return redirect(back)
    if _is_last_admin(db, target) and (not is_active or role.name != perms.SUPER_ROLE):
        flash(request, "error", "C'est le dernier administrateur actif : il doit le rester.")
        return redirect(back)
    if password or password_confirm:
        error = passwords.pair_error(password, password_confirm)
        if error:
            flash(request, "error", error)
            return redirect(back)

    changes: dict = {}
    if clean_email != target.email:
        changes["email"] = [target.email, clean_email]
        target.email = clean_email
    if role.id != target.role_id:
        changes["role"] = [target.role.name, role.name]
        target.role_id = role.id
    if is_active != target.is_active:
        changes["active"] = [target.is_active, is_active]
        target.is_active = is_active
    if password:
        target.password_hash = passwords.hash_password(password)
        changes["password"] = "modifié"  # noqa: S105 - libellé d'audit
    if reset_totp and target.totp_enabled:
        target.totp_secret, target.totp_enabled, target.totp_last_step = None, False, None
        changes["totp"] = "réinitialisée"
    if not changes:
        flash(request, "info", "Aucune modification.")
        return redirect(back)
    if not target.is_active or password or "role" in changes:
        revoke_user_sessions(db, target.id)
    _log(db, request, actor, "user.update", settings, "user", target.id, username=target.username, **changes)
    db.commit()
    flash(request, "success", f"Utilisateur « {target.username} » mis à jour.")
    return redirect("/admin/users")


@router.post("/users/{user_id}/delete")
def user_delete(
    request: Request,
    user_id: int,
    actor: User = Depends(require_permission(perms.USERS_MANAGE)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    target = db.get(User, user_id)
    if target is None:
        return redirect("/admin/users")
    if target.id == actor.id:
        flash(request, "error", "Vous ne pouvez pas supprimer votre propre compte.")
        return redirect(f"/admin/users/{user_id}")
    if _is_last_admin(db, target):
        flash(request, "error", "Impossible de supprimer le dernier administrateur actif.")
        return redirect(f"/admin/users/{user_id}")
    name = target.username
    revoke_user_sessions(db, target.id)
    db.delete(target)
    _log(db, request, actor, "user.delete", settings, "user", user_id, username=name)
    db.commit()
    flash(request, "success", f"Utilisateur « {name} » supprimé.")
    return redirect("/admin/users")


# =========================================================================== rôles


@router.get("/roles")
def roles_page(
    request: Request, actor: User = Depends(require_permission(perms.ROLES_MANAGE)), db: Session = Depends(get_db)
):
    roles = db.scalars(select(Role).order_by(Role.id)).all()
    counts = dict(db.execute(select(User.role_id, func.count()).group_by(User.role_id)).all())
    return render(
        request,
        "admin/roles.html",
        active="roles",
        roles=roles,
        catalog=perms.CATALOG,
        counts=counts,
        super_role=perms.SUPER_ROLE,
        locked=perms.SUPER_ROLE_LOCKED,
    )


@router.post("/roles")
async def roles_save(
    request: Request,
    actor: User = Depends(require_permission(perms.ROLES_MANAGE)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    form = await request.form()
    roles = db.scalars(select(Role)).all()
    changed = {}
    for role in roles:
        wanted = {k for k in form.getlist(f"perm_{role.id}") if k in perms.CATALOG}
        if role.name == perms.SUPER_ROLE:
            wanted |= perms.SUPER_ROLE_LOCKED
        current = role.permission_keys
        if wanted != current:
            role.permissions = [p for p in role.permissions if p.permission_key in wanted]
            for key in sorted(wanted - current):
                role.permissions.append(RolePermission(permission_key=key))
            changed[role.name] = {"ajout": sorted(wanted - current), "retrait": sorted(current - wanted)}
    if changed:
        _log(db, request, actor, "role.update", settings, "role", None, **changed)
        db.commit()
        flash(request, "success", "Permissions enregistrées.")
    else:
        flash(request, "info", "Aucune modification.")
    return redirect("/admin/roles")


@router.post("/roles/new")
def role_create(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    actor: User = Depends(require_permission(perms.ROLES_MANAGE)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    name = name.strip().lower()
    if not name or len(name) > 50 or not name.replace("_", "").replace("-", "").isalnum():
        flash(request, "error", "Nom de rôle invalide (lettres, chiffres, tiret ou soulignement).")
        return redirect("/admin/roles")
    if db.scalar(select(Role.id).where(Role.name == name)):
        flash(request, "error", "Ce rôle existe déjà.")
        return redirect("/admin/roles")
    role = Role(name=name, description=description.strip()[:255] or name.capitalize())
    db.add(role)
    db.flush()
    _log(db, request, actor, "role.create", settings, "role", role.id, name=name)
    db.commit()
    flash(request, "success", f"Rôle « {role.description} » créé. Cochez ses permissions.")
    return redirect("/admin/roles")


@router.post("/roles/{role_id}/delete")
def role_delete(
    request: Request,
    role_id: int,
    actor: User = Depends(require_permission(perms.ROLES_MANAGE)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    role = db.get(Role, role_id)
    if role is None:
        return redirect("/admin/roles")
    if role.name == perms.SUPER_ROLE or role.users:
        flash(request, "error", "Ce rôle ne peut pas être supprimé : il est protégé ou attribué à des utilisateurs.")
        return redirect("/admin/roles")
    name = role.name
    db.delete(role)
    _log(db, request, actor, "role.delete", settings, "role", role_id, name=name)
    db.commit()
    flash(request, "success", f"Rôle « {name} » supprimé.")
    return redirect("/admin/roles")


# =========================================================================== audit

PERIODS = {7: "7 derniers jours", 30: "30 derniers jours", 90: "90 derniers jours", 365: "12 derniers mois"}
AUDIT_PAGE_SIZE = 200


def _audit_query(period: int, kind: str, q: str):
    days = period if period in PERIODS else 30
    stmt = select(AuditLog).where(AuditLog.created_at >= utcnow() - timedelta(days=days))
    if kind in audit.CATEGORIES:
        stmt = stmt.where(AuditLog.action.like(f"{kind}.%"))
    for word in _words(q):
        pattern = _like(word)
        stmt = stmt.where(
            or_(
                AuditLog.actor_username.ilike(pattern, escape="\\"),
                AuditLog.action.ilike(pattern, escape="\\"),
                AuditLog.ip_address.ilike(pattern, escape="\\"),
                AuditLog.details.ilike(pattern, escape="\\"),
            )
        )
    return stmt.order_by(AuditLog.id.desc())


def _details_text(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    return " · ".join(f"{k} : {v}" for k, v in data.items()) if isinstance(data, dict) else str(data)


@router.get("/audit")
def audit_page(
    request: Request,
    period: int = 30,
    kind: str = "",
    q: str = "",
    actor: User = Depends(require_permission(perms.AUDIT_VIEW)),
    db: Session = Depends(get_db),
):
    stmt = _audit_query(period, kind, q)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    entries = db.scalars(stmt.limit(AUDIT_PAGE_SIZE)).all()
    failed = (
        db.scalar(
            select(func.count()).select_from(
                stmt.order_by(None).where(AuditLog.action == "auth.login_failed").subquery()
            )
        )
        or 0
    )
    return render(
        request,
        "admin/audit.html",
        active="audit",
        entries=entries,
        total=total,
        failed=failed,
        page_size=AUDIT_PAGE_SIZE,
        periods=PERIODS,
        categories=audit.CATEGORIES,
        label=audit.action_label,
        details=_details_text,
        filters={"period": period if period in PERIODS else 30, "kind": kind, "q": q},
        query=request.url.query,
    )


@router.get("/audit/export.{fmt}")
def audit_export(
    fmt: str,
    period: int = 30,
    kind: str = "",
    q: str = "",
    actor: User = Depends(require_permission(perms.AUDIT_VIEW)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    entries = db.scalars(_audit_query(period, kind, q)).all()
    headers = ["Date", "Action", "Acteur", "Cible", "Détails", "Adresse IP"]
    rows = [
        [
            e.created_at,
            audit.action_label(e.action),
            e.actor_username,
            f"{e.target_type or ''} {e.target_id or ''}".strip(),
            _details_text(e.details),
            e.ip_address,
        ]
        for e in entries
    ]
    if fmt == "xlsx":
        return xlsx_response("journal-audit", "Journal", headers, rows, settings.timezone)
    return csv_response("journal-audit", headers, rows, settings.timezone)


# =========================================================================== à propos


@router.get("/about")
def about_page(
    request: Request, actor: User = Depends(require_permission(perms.ADMIN_ACCESS)), db: Session = Depends(get_db)
):
    try:
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:  # noqa: BLE001 - table absente si la base a été créée sans Alembic
        revision = None
    info = {
        "Version de l'application": __version__,
        "Python": platform.python_version(),
        "Base de données": db.get_bind().dialect.name,
        "Migration appliquée": revision or "—",
        "Utilisateurs": db.scalar(select(func.count()).select_from(User)),
    }
    return render(request, "admin/about.html", active="about", info=info, changelog=CHANGELOG)
