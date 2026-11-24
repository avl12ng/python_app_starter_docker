# 03 · Configuration

Toute la configuration vient du fichier `.env` (modèle : `.env.example`). L'application lit ces valeurs avec
`app/config.py` (classe `Settings`) : le nom de la variable est celui du champ, en majuscules.
Après une modification, relancer : `docker compose up -d app`.

## Application (`app/config.py`)

| Variable | Défaut | Rôle |
|----------|--------|------|
| `APP_NAME` | `Application` | Nom affiché (titre des onglets, e-mails, libellé dans l'application 2FA) |
| `APP_SHORT` | `APP` | Sigle affiché en jaune à côté du logo |
| `ORG_NAME` | `Organisation` | Nom affiché à côté du logo, tronqué s'il est trop long (le logo lui-même est `app/static/img/logo.svg`) |
| `TIMEZONE` | `Europe/Paris` | Fuseau d'affichage des dates (stockées en UTC) |
| `DEBUG` | `false` | `true` : journaux détaillés et documentation de l'API sur `/api/docs`. **Jamais en production** |
| `SECRET_KEY` | — (obligatoire) | 32 caractères minimum. Signe les codes de réinitialisation. La changer invalide les codes en cours, sans autre effet |
| `DATABASE_URL` | `sqlite:///./data/app.db` | Fourni par `docker-compose.yml` à partir des variables `DB_*` ; à définir soi-même hors Docker |
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8095` | Écoute de `python -m app.serve` (Windows / sans Docker). Ignorés sous Docker |
| `WEB_WORKERS` | `1` | Nombre de processus web (Docker et sans Docker) |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Proxy autorisé à transmettre l'IP et le protocole d'origine |
| `SSL_CERTFILE` / `SSL_KEYFILE` | vides | HTTPS direct sans reverse-proxy (fichiers PEM). Vides : HTTP |
| `SESSION_COOKIE` | `app_session` | Nom du cookie. À changer si deux applications partagent le même domaine |
| `SESSION_IDLE_MINUTES` | `120` | Déconnexion après cette durée d'inactivité (5 à 1440) |
| `COOKIE_SECURE` | `auto` | `auto` : `Secure` si la requête arrive en HTTPS ; `true` / `false` pour forcer |
| `LOGIN_MAX_FAILED_ACCOUNT` | `8` | Échecs tolérés sur un même compte (toutes adresses confondues) |
| `LOGIN_MAX_FAILED_PER_IP_USER` | `12` | Échecs tolérés pour un couple compte + adresse IP |
| `LOGIN_MAX_FAILED_PER_IP` | `40` | Échecs tolérés pour une adresse IP, tous comptes confondus |
| `LOGIN_MAX_FAILED_TOTP` | `6` | Codes 2FA faux tolérés pour un compte |
| `LOGIN_LOCKOUT_MINUTES` | `15` | Fenêtre de comptage et durée du verrouillage |
| `RESET_TTL_MINUTES` | `10` | Validité d'un code de réinitialisation |
| `RESET_MAX_PER_IP_HOUR` | `15` | Demandes de code + codes faux tolérés par adresse IP et par heure |
| `AUDIT_RETENTION_DAYS` | `365` | Durée de conservation du journal d'audit |
| `SMTP_HOST` | vide | Vide : les e-mails sont écrits dans les journaux du conteneur au lieu d'être envoyés |
| `SMTP_PORT` | `587` | |
| `SMTP_SECURITY` | `starttls` | `starttls` (587), `ssl` (465) ou `none` |
| `SMTP_USER`, `SMTP_PASSWORD` | vide | Identifiants SMTP (vides : pas d'authentification) |
| `SMTP_FROM` | `no-reply@example.local` | Expéditeur. Doit être autorisé par le serveur SMTP |

## Docker Compose (`docker-compose.yml`, `docker/app/Dockerfile`)

| Variable | Défaut | Rôle |
|----------|--------|------|
| `COMPOSE_PROJECT_NAME` | `pyapp` | Préfixe des conteneurs, volumes et réseau |
| `WEB_PUBLISH_ADDRESS` / `WEB_PUBLISH_PORT` | `0.0.0.0` / `8095` | Adresse et port publiés pour l'application |
| `TZ` | `Europe/Paris` | Fuseau des conteneurs (journaux) |
| `PYTHON_VERSION` | `3.13` | Version de Python de l'image |
| `APP_IMAGE` / `APP_IMAGE_TAG` | `python-app-starter` / `latest` | Nom de l'image construite |
| `APP_CONTAINER_NAME` / `DB_CONTAINER_NAME` | `pyapp_app` / `pyapp_db` | Noms des conteneurs |
| `DB_DATABASE` / `DB_USERNAME` | `pyapp` / `pyapp` | Base et compte applicatif créés au premier démarrage de MariaDB |
| `DB_PASSWORD` / `DB_ROOT_PASSWORD` | — (obligatoires) | Lettres et chiffres uniquement |
| `DB_PUBLISH_ADDRESS` / `DB_PUBLISH_PORT` | `127.0.0.1` / `3395` | Accès à la base depuis la machine hôte (outil SQL) |
| `MARIADB_VERSION` | `11.8` | Version de l'image MariaDB |
| `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD` | vides | **Facultatif.** Crée l'administrateur au démarrage si la base n'a aucun compte (sinon : page **Première configuration**). Vider le mot de passe ensuite |

> `DB_PASSWORD` et `DB_ROOT_PASSWORD` ne sont lus par MariaDB qu'à la **création** du volume. Les changer
> ensuite dans `.env` ne change pas les comptes existants : il faut aussi les modifier dans MariaDB.

## Réglages en base

Les rôles et leurs permissions se règlent dans **Administration › Rôles et permissions** (tables `roles` et
`role_permissions`). Le catalogue des permissions est défini dans le code (`app/core/permissions.py`).
