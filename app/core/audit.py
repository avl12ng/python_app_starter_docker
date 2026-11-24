"""Journal d'audit des actions sensibles."""

from __future__ import annotations

import json
import logging
import random
from datetime import timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import AuditLog, User

log = logging.getLogger(__name__)

# Libellés affichés dans le journal. Ajouter ici les actions du moteur métier.
ACTIONS: dict[str, str] = {
    "auth.login": "Connexion",
    "auth.login_failed": "Échec de connexion",
    "auth.logout": "Déconnexion",
    "auth.password_reset_request": "Demande de réinitialisation",
    "auth.password_reset": "Mot de passe réinitialisé",
    "account.password_change": "Mot de passe modifié",
    "account.email_change": "Courriel modifié",
    "account.totp_enable": "Double authentification activée",
    "account.totp_disable": "Double authentification désactivée",
    "user.create": "Utilisateur créé",
    "user.update": "Utilisateur modifié",
    "user.delete": "Utilisateur supprimé",
    "role.create": "Rôle créé",
    "role.update": "Permissions modifiées",
    "role.delete": "Rôle supprimé",
    "engine.run": "Calcul lancé",
}

CATEGORIES: dict[str, str] = {
    "auth": "Connexions",
    "account": "Comptes",
    "user": "Utilisateurs",
    "role": "Rôles",
    "engine": "Moteur",
}


def action_label(action: str) -> str:
    return ACTIONS.get(action, action)


def record(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    actor_username: str | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    details: dict[str, Any] | None = None,
    ip: str = "",
    retention_days: int = 365,
) -> None:
    """Ajoute une entrée (à valider par le db.commit() de l'appelant)."""
    db.add(
        AuditLog(
            user_id=actor.id if actor else None,
            actor_username=(actor.username if actor else (actor_username or ""))[:50],
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            ip_address=ip[:45],
            created_at=utcnow(),
        )
    )
    if random.random() < 0.01:  # noqa: S311 - purge occasionnelle au-delà de la durée de conservation
        db.execute(delete(AuditLog).where(AuditLog.created_at < utcnow() - timedelta(days=retention_days)))
