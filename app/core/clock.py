"""Heures en UTC en base, affichage en heure locale et formats français (JJ/MM/AAAA, semaine ISO)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def utcnow() -> datetime:
    """Heure UTC sans fuseau (format stocké en base, identique sous MariaDB et SQLite)."""
    return datetime.now(UTC).replace(tzinfo=None)


@lru_cache
def _zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def to_local(value: datetime | None, tz: str = "Europe/Paris") -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(_zone(tz))


def date_fr(value: date | datetime | None, tz: str = "Europe/Paris") -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = to_local(value, tz)
    return value.strftime("%d/%m/%Y")


def datetime_fr(value: datetime | None, tz: str = "Europe/Paris") -> str:
    local = to_local(value, tz)
    return local.strftime("%d/%m/%Y %H:%M") if local else ""


def long_date_fr(value: date) -> str:
    """« mardi 24 novembre 2026 »."""
    return f"{JOURS[value.weekday()]} {value.day} {MOIS[value.month - 1]} {value.year}"


def week_label(value: date) -> str:
    """Numéro de semaine ISO : « S48 »."""
    return f"S{value.isocalendar().week:02d}"
