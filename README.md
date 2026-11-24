# Python App Starter

Squelette d'application web **Python** prêt à recevoir un moteur de calcul métier. Il fournit déjà
une authentification sécurisée complète et l'administration des comptes, dans la charte graphique
de *digitization_commercial*. Logo et nom de l'organisation se remplacent sans toucher au code
(`app/static/img/logo.svg`, `ORG_NAME`).

La partie authentification reprend les fonctionnalités et les règles de sécurité de
*secure_website_starter* (PHP), réécrites en Python avec FastAPI.

## Fonctionnalités

| Domaine | Ce qui est en place |
|---------|---------------------|
| Première configuration | Création du compte administrateur depuis le navigateur au premier lancement, rien à mettre dans `.env` |
| Connexion | Identifiant + mot de passe (Argon2id), session côté serveur révocable, expiration après inactivité |
| Double authentification | TOTP (Google/Microsoft Authenticator, FreeOTP), QR code généré localement, anti-rejeu |
| Anti force brute | Verrouillage temporaire par compte, par poste et par adresse IP ; limitation des demandes de code |
| Mot de passe oublié | Code à 10 chiffres envoyé par courriel, valable 10 min, sans révéler si le compte existe |
| Mon compte | Changer son courriel, son mot de passe (déconnecte les autres sessions), activer ou couper la 2FA |
| Administration | Utilisateurs (création, rôle, désactivation, réinitialisation 2FA), rôles et permissions, journal d'audit, à propos |
| Listes | Recherche et filtres pendant la frappe, exports **CSV** (format français) et **Excel** |
| Sécurité HTTP | CSRF sur tous les envois, CSP stricte (aucun script en ligne), en-têtes durcis, redirections locales uniquement |
| Moteur | Module `app/engine/` d'exemple, appelable depuis une page web et une API JSON, protégé par permission |

## Stack

Python 3.12+ · FastAPI · Jinja2 · SQLAlchemy 2 · Alembic · MariaDB (SQLite en développement) · uvicorn · Docker Compose.
Aucun CDN : polices, icônes et scripts sont servis par l'application.

## Démarrage rapide

### Avec Docker (comme en production)

```bash
cp .env.example .env
# Renseigner au minimum : SECRET_KEY, DB_PASSWORD, DB_ROOT_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # → valeur pour SECRET_KEY
docker compose up -d --build
```

Ouvrir `http://localhost:8095` : à la première utilisation, la page **Première configuration** demande
l'identifiant, le courriel et le mot de passe du compte administrateur. Elle disparaît dès que ce compte existe.

> Faire cette étape avant d'ouvrir l'application sur Internet : tant qu'aucun compte n'existe, la première
> personne qui ouvre la page devient administrateur.

### Sur Windows, sans Docker

Prérequis : Python 3.12+ installé avec l'option **Add python.exe to PATH**. Ensuite :

| Script | Effet |
|--------|-------|
| `windows\install.bat` | Environnement Python, dépendances, `.env`, base SQLite (à relancer après une mise à jour) |
| `windows\start.bat` | Lance l'application → `http://localhost:8095` |
| `windows\backup.bat` | Sauvegarde à chaud de la base dans `backups\` |

Port, HTTPS et nom de l'application se règlent dans `.env`. Mode opératoire complet (pare-feu, HTTPS,
démarrage automatique, sauvegarde planifiée) : [docs/technique/02-deploiement-windows.md](docs/technique/02-deploiement-windows.md).

### En local, sans Docker (développement)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # SECRET_KEY obligatoire ; DATABASE_URL=sqlite:///./data/app.db
echo "DATABASE_URL=sqlite:///./data/app.db" >> .env
alembic upgrade head
uvicorn --factory app.main:create_app --reload
```

→ `http://127.0.0.1:8000` (page **Première configuration** au premier lancement). Sans `SMTP_HOST`, les codes de réinitialisation s'affichent dans la console.

## Brancher le moteur Python

Le moteur vit dans [app/engine/core.py](app/engine/core.py) : une fonction `run()` qui reçoit des données Python
et renvoie un résultat, sans rien savoir du web. Remplacer l'exemple (statistiques descriptives) par le calcul
métier, puis adapter la page [engine.html](app/templates/engine/engine.html) et les routes de
[app/engine/routes.py](app/engine/routes.py). Pas à pas : [docs/technique/07-developpement.md](docs/technique/07-developpement.md).

## Commandes utiles

| Commande | Effet |
|----------|-------|
| `pytest` | Tests (SQLite ; `TEST_DATABASE_URL=…` pour MariaDB) |
| `ruff check . && ruff format --check .` | Qualité du code |
| `alembic revision --autogenerate -m "…"` | Nouvelle migration après modification de `app/models.py` |
| `alembic upgrade head` | Appliquer les migrations (fait automatiquement au démarrage du conteneur) |
| `python -m app.cli create-admin --username … --email …` | Créer un administrateur en ligne de commande (dépannage) |
| `python -m app.cli backup` | Sauvegarde à chaud de la base SQLite dans `backups/` |
| `python -m app.cli set-password --username …` | Changer un mot de passe en ligne de commande |
| `docker compose exec app python -m app.cli …` | Les mêmes commandes dans le conteneur |

## Arborescence

```
app/
  main.py            création de l'application, gestion des erreurs, accueil
  config.py          configuration (variables d'environnement / .env)
  models.py          tables SQLAlchemy
  web.py             rendu des gabarits, menu selon les permissions, messages
  core/              sécurité : sessions, CSRF, mots de passe, TOTP, permissions, audit, exports, e-mail
  auth/              connexion, 2FA, mot de passe oublié
  account/           « Mon compte »
  admin/             utilisateurs, rôles, journal d'audit, à propos
  engine/            ← moteur métier (core.py) et ses écrans (routes.py)
  templates/         gabarits Jinja2
  static/            CSS de la charte, JavaScript, police, logo
migrations/          migrations Alembic
tests/               tests pytest
docker/              Dockerfile, script de démarrage, configuration MariaDB
windows/             scripts .bat : installation, lancement, sauvegarde (Windows sans Docker)
docs/technique/      documentation technique (architecture, déploiement, exploitation…)
```

## Documentation

- [Documentation technique](docs/technique/README.md) : architecture, déploiement, configuration, données,
  règles de sécurité, développement, exploitation.
- Mode d'emploi utilisateur : à rédiger quand les écrans métier existeront (voir la documentation technique).

## Licence

MIT, voir [LICENSE](LICENSE). La police Hanken Grotesk est sous licence SIL OFL 1.1
([app/static/fonts/HankenGrotesk-OFL.txt](app/static/fonts/HankenGrotesk-OFL.txt)).
