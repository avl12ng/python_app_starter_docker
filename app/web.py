"""Rendu des gabarits Jinja2 : contexte commun, filtres français, messages flash, menu selon les droits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app import __version__
from app.config import Settings
from app.core import clock, permissions
from app.core.icons import ICONS
from app.core.security import csrf_token
from app.models import User

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@dataclass(frozen=True)
class NavItem:
    id: str
    label: str
    href: str
    icon: str
    permission: str | None = None
    section: str = "main"


# Menu latéral. Ajouter ici les écrans du moteur (section « main ») ; les écrans de gestion
# vont dans la section « admin ». Le contrôle d'accès est AUSSI fait côté serveur sur chaque route.
NAV: list[NavItem] = [
    NavItem("home", "Accueil", "/", "dashboard"),
    NavItem("engine", "Moteur", "/engine", "science", permissions.ENGINE_RUN),
    NavItem("users", "Utilisateurs", "/admin/users", "group", permissions.USERS_MANAGE, "admin"),
    NavItem("roles", "Rôles et permissions", "/admin/roles", "shield", permissions.ROLES_MANAGE, "admin"),
    NavItem("audit", "Journal d'audit", "/admin/audit", "history", permissions.AUDIT_VIEW, "admin"),
    NavItem("about", "À propos", "/admin/about", "info", permissions.ADMIN_ACCESS, "admin"),
]


def nav_for(user: User | None) -> list[NavItem]:
    if user is None:
        return []
    return [item for item in NAV if item.permission is None or user.can(item.permission)]


def icon(name: str, size: int = 22) -> Markup:
    body = ICONS.get(name, "")
    return Markup(  # noqa: S704 - tracés SVG statiques de app/core/icons.py
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )


def flash(request: Request, kind: str, message: str) -> None:
    """kind : success | error | info"""
    messages = list(request.state.session.get("_flash", []))
    messages.append([kind, message])
    request.state.session["_flash"] = messages


def _consume_flashes(request: Request) -> list:
    return request.state.session.pop("_flash", None) or []


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


_tz = {"name": "Europe/Paris"}


def configure(settings: Settings) -> None:
    """Appelé par create_app : fuseau horaire utilisé par les filtres de date."""
    _tz["name"] = settings.timezone


def render(request: Request, template: str, status_code: int = 200, **context):
    settings: Settings = request.app.state.settings
    user: User | None = getattr(request.state, "user", None)
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    ctx = {
        "settings": settings,
        "user": user,
        "nav": nav_for(user),
        "active": context.pop("active", None),
        "csrf_token": csrf_token(request),
        "asset_version": __version__,
        "flashes": _consume_flashes(request),
        "today_label": f"{clock.long_date_fr(today).capitalize()} · {clock.week_label(today)}",
        **context,
    }
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)


templates.env.globals["icon"] = icon
templates.env.filters["date_fr"] = lambda v: clock.date_fr(v, _tz["name"])
templates.env.filters["datetime_fr"] = lambda v: clock.datetime_fr(v, _tz["name"])
templates.env.filters["week"] = clock.week_label
