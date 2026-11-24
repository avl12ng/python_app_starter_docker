"""Catalogue des permissions. Chaque rôle reçoit une liste de clés (table role_permissions).

Pour ajouter une permission : la déclarer ici, puis la cocher pour les rôles concernés dans
Administration › Rôles et permissions (ou dans une migration si elle doit exister d'office).
"""

from __future__ import annotations

ADMIN_ACCESS = "admin.access"
USERS_MANAGE = "users.manage"
ROLES_MANAGE = "roles.manage"
AUDIT_VIEW = "audit.view"
ENGINE_RUN = "engine.run"

CATALOG: dict[str, str] = {
    ADMIN_ACCESS: "Accéder à l'administration",
    USERS_MANAGE: "Gérer les utilisateurs",
    ROLES_MANAGE: "Gérer les rôles et permissions",
    AUDIT_VIEW: "Consulter le journal d'audit",
    ENGINE_RUN: "Utiliser le moteur de calcul",
}

ADMIN_PERMISSIONS = {ADMIN_ACCESS, USERS_MANAGE, ROLES_MANAGE, AUDIT_VIEW}

# Rôle protégé : il garde toujours ces permissions pour qu'on ne puisse pas s'enfermer dehors.
SUPER_ROLE = "admin"
SUPER_ROLE_LOCKED = {ADMIN_ACCESS, USERS_MANAGE, ROLES_MANAGE}
