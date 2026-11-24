# 02 · Déploiement

Mode opératoire exécutable dans l'ordre. Valeurs d'exemple : serveur `srv-docker`, adresse publique
`https://app.exemple.fr`.

## Prérequis

- Docker Engine 24+ et Docker Compose v2 (`docker compose version`).
- Un reverse-proxy HTTPS devant l'application (Nginx Proxy Manager, Traefik, Nginx…). L'application elle-même
  écoute en HTTP sur le port 8000 du conteneur.
- Un compte SMTP pour l'envoi des codes de réinitialisation (facultatif au début).

## Première installation

1. Récupérer le dépôt :
   ```bash
   git clone <url-du-depot> python_app_starter && cd python_app_starter
   ```
2. Créer la configuration :
   ```bash
   cp .env.example .env
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
   python3 -c "import secrets; print(secrets.token_hex(16))"       # DB_PASSWORD, puis DB_ROOT_PASSWORD
   ```
   Renseigner dans `.env` : `SECRET_KEY`, `DB_PASSWORD`, `DB_ROOT_PASSWORD`, `APP_NAME` et `APP_SHORT`.

   > **Mots de passe de base** : lettres et chiffres uniquement. Ils entrent dans l'URL de connexion
   > `DATABASE_URL`, où `@`, `:` ou `/` casseraient l'analyse.

3. Construire et démarrer :
   ```bash
   docker compose up -d --build
   docker compose logs -f app
   ```
   Sortie attendue (extrait) :
   ```
   pyapp_app  | Attente de la base de données…
   pyapp_app  | Migrations…
   pyapp_app  | INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Schéma initial : …
   Aucun compte : ouvrez l'application dans un navigateur pour créer l'administrateur (page « Première configuration »).
   pyapp_app  | INFO:     Application startup complete.
   ```
4. Ouvrir `http://srv-docker:8095` : la page **Première configuration** demande l'identifiant, le courriel et
   le mot de passe (12 caractères minimum, avec majuscule, minuscule, chiffre et caractère spécial) du compte
   administrateur. Une fois le compte créé, on est connecté, et la page n'est plus accessible.

   > **À faire avant d'exposer l'application** (reverse-proxy, ouverture de port) : tant qu'aucun compte
   > n'existe, la première personne qui ouvre la page devient administrateur.

   *Installation automatisée* : renseigner `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_EMAIL` et
   `INITIAL_ADMIN_PASSWORD` dans `.env` avant le premier démarrage. Le compte est alors créé au démarrage et
   la page de configuration n'apparaît pas. Vider ensuite le mot de passe.

## Reverse-proxy HTTPS

Dans le proxy, faire pointer `app.exemple.fr` vers `http://srv-docker:8095`, avec un certificat Let's Encrypt.
Ensuite, dans `.env` :

| Variable | Valeur | Pourquoi |
|----------|--------|----------|
| `FORWARDED_ALLOW_IPS` | IP du proxy **vue depuis le conteneur** (ex. `172.18.0.1` si le proxy est sur l'hôte, ou l'IP du conteneur proxy) | uvicorn ne fait confiance aux en-têtes `X-Forwarded-For` / `-Proto` que s'ils viennent de cette adresse |
| `COOKIE_SECURE` | `auto` (défaut) ou `true` | Avec `auto`, le cookie devient `Secure` et l'en-tête HSTS est envoyé dès que le proxy annonce HTTPS |
| `WEB_PUBLISH_ADDRESS` | `127.0.0.1` si le proxy est sur la même machine | Empêche l'accès direct en HTTP depuis le réseau |

> **Piège** : si `FORWARDED_ALLOW_IPS` est mal réglé, l'application voit l'IP du proxy pour tout le monde.
> Le verrouillage par adresse IP bloque alors **tous** les utilisateurs après 40 échecs cumulés.
> Vérifier dans **Administration › Journal d'audit** que la colonne « Adresse IP » montre bien les postes
> des utilisateurs. `FORWARDED_ALLOW_IPS=*` fonctionne mais fait confiance à n'importe qui : à n'utiliser que
> si le port de l'application n'est joignable que par le proxy.

Appliquer : `docker compose up -d app`.

## Mise à jour

```bash
# 1. Sauvegarder la base (voir 08-exploitation.md)
# 2. Récupérer et reconstruire
git pull
docker compose up -d --build
docker compose logs --tail 30 app     # migrations appliquées, « Application startup complete »
```

Les migrations Alembic s'appliquent automatiquement au démarrage du conteneur.

## Retour arrière

1. Revenir au code précédent : `git checkout <tag-ou-commit-précédent>`.
2. Si la version annulée contenait une migration, **restaurer la sauvegarde** faite avant la mise à jour
   (08-exploitation.md). Un `alembic downgrade` est possible, mais la restauration est plus sûre en production.
3. `docker compose up -d --build`.

## Recette après installation ou mise à jour

| Vérification | Résultat attendu |
|--------------|------------------|
| `curl -s http://127.0.0.1:8095/health` | `{"status":"ok"}` |
| `docker compose ps` | `pyapp_app` et `pyapp_db` en `(healthy)` |
| Première configuration, puis connexion avec le compte administrateur | Accueil « Bonjour … » |
| **Mon compte › Activer la double authentification** | QR code affiché, code accepté |
| **Mot de passe oublié** depuis la page de connexion | Code reçu par courriel (ou dans `docker compose logs app` sans SMTP) |
| **Administration › Journal d'audit** | Connexions visibles, avec la vraie IP des postes |
| `curl -sI https://app.exemple.fr/login` | `set-cookie: … HttpOnly; … SameSite=lax; Secure` et `strict-transport-security` |
