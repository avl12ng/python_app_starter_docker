# 05 · Données

## Schéma

```mermaid
erDiagram
  roles ||--o{ role_permissions : "a"
  roles ||--o{ users : "attribué à"
  users ||--o{ auth_password_resets : "demande"
  users ||..o{ web_sessions : "ouvre"
  users ||..o{ audit_log : "agit"

  roles {
    int id PK
    string name UK
    string description
  }
  role_permissions {
    int id PK
    int role_id FK
    string permission_key
  }
  users {
    int id PK
    string username UK
    string email UK
    string password_hash
    int role_id FK
    bool is_active
    string totp_secret
    bool totp_enabled
    bigint totp_last_step
    datetime last_login_at
  }
  auth_login_attempts {
    bigint id PK
    string kind
    string username
    string ip_address
    bool success
    datetime attempted_at
  }
  auth_password_resets {
    bigint id PK
    int user_id FK
    string token_hash
    datetime expires_at
    datetime used_at
  }
  audit_log {
    bigint id PK
    int user_id
    string actor_username
    string action
    string target_type
    string target_id
    text details
    string ip_address
    datetime created_at
  }
  web_sessions {
    string id PK
    int user_id
    text data
    datetime last_seen_at
  }
```

Les liens en pointillés ne sont pas des clés étrangères : une ligne du journal ou une session reste lisible
même après la suppression du compte.

## Rôle des tables

| Table | Contenu | Remarques |
|-------|---------|-----------|
| `roles` | Rôles : `admin` (Administrateur), `manager` (Responsable), `user` (Utilisateur) | Créés par la migration `0001`. `admin` ne peut pas être supprimé |
| `role_permissions` | Permissions de chaque rôle | Clés définies dans `app/core/permissions.py` |
| `users` | Comptes | Mot de passe haché en Argon2id ; `totp_last_step` empêche de rejouer un code 2FA |
| `auth_login_attempts` | Tentatives : `login`, `totp`, `reset_request`, `reset_fail` | Sert au verrouillage (fenêtre glissante). Peut être vidée sans risque |
| `auth_password_resets` | Codes de réinitialisation | Seule une empreinte HMAC-SHA256 du code est stockée |
| `audit_log` | Journal des actions sensibles | Purgé au-delà de `AUDIT_RETENTION_DAYS` |
| `web_sessions` | Sessions ouvertes | `id` = empreinte SHA-256 du jeton du cookie. Vider la table déconnecte tout le monde |
| `alembic_version` | Révision du schéma | Gérée par Alembic |

Toutes les dates sont stockées en **UTC** et affichées dans le fuseau `TIMEZONE`.

## Permissions par défaut

| Permission | Libellé | admin | manager | user |
|------------|---------|:-----:|:-------:|:----:|
| `admin.access` | Accéder à l'administration (page À propos) | ✔ (verrouillé) | | |
| `users.manage` | Gérer les utilisateurs | ✔ (verrouillé) | | |
| `roles.manage` | Gérer les rôles et permissions | ✔ (verrouillé) | | |
| `audit.view` | Consulter le journal d'audit | ✔ | ✔ | |
| `engine.run` | Utiliser le moteur de calcul | ✔ | ✔ | ✔ |

## Migrations

- Outil : Alembic, fichiers dans `migrations/versions/`.
- Appliquées automatiquement au démarrage du conteneur (`docker/app/entrypoint.sh`).
- Nouvelle table ou colonne : modifier `app/models.py`, puis
  `alembic revision --autogenerate -m "ajout table mesures"`. **Relire** le fichier généré : l'autogénération
  ne voit ni les renommages ni les données à reprendre.
- Ne jamais modifier une migration déjà appliquée en production : en créer une nouvelle.
