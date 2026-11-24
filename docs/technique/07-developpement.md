# 07 · Développement

## Environnement local

```bash
python3 -m venv .venv && . .venv/bin/activate      # Windows : windows\install.bat puis windows\start.bat
pip install -e ".[dev]"
cp .env.example .env
# Dans .env : SECRET_KEY=<valeur aléatoire> et DATABASE_URL=sqlite:///./data/app.db
alembic upgrade head
uvicorn --factory app.main:create_app --reload
```

Au premier lancement, `http://127.0.0.1:8000` affiche la page **Première configuration** pour créer
l'administrateur. Pour repartir de zéro : supprimer `data/app.db` et relancer `alembic upgrade head`.

Avec `DEBUG=true`, la documentation de l'API est servie sur `http://127.0.0.1:8000/api/docs`.

## Tests et qualité

| Commande | Effet |
|----------|-------|
| `pytest` | 28 tests sur une base SQLite temporaire, créée par les migrations Alembic |
| `TEST_DATABASE_URL="mysql+pymysql://root:root@127.0.0.1:3306/app_test?charset=utf8mb4" pytest` | Mêmes tests sur MariaDB (base vidée à chaque test) |
| `ruff check .` / `ruff format .` | Lint (dont règles de sécurité Bandit `S`) et formatage |

La CI GitHub (`.github/workflows/ci.yml`) lance le lint, les tests sur SQLite, les tests sur MariaDB 11.8 et la
construction de l'image Docker à chaque push sur `main` / `develop` et à chaque pull request.

## Brancher le moteur métier

Le moteur est isolé dans `app/engine/core.py` : il reçoit des données Python, renvoie un résultat, et ne
connaît ni FastAPI, ni la session, ni la base. On peut ainsi le tester seul et le faire évoluer sans toucher à
l'authentification.

1. **Remplacer le calcul** : réécrire `EngineInput`, `EngineResult` et `run()` dans `app/engine/core.py`.
   Lever `EngineError("message")` pour une erreur de saisie : le message est affiché tel quel.
   Le moteur existe déjà sous forme de paquet ? L'ajouter aux `dependencies` de `pyproject.toml` et l'appeler
   depuis `run()`.
2. **Adapter l'écran** : formulaire et affichage du résultat dans `app/templates/engine/engine.html`, lecture
   des champs dans `engine_submit()` (`app/engine/routes.py`).
3. **API JSON** (facultatif) : `POST /api/engine/run`. Depuis le JavaScript de l'application,
   `await window.appFetch('/api/engine/run', {method: 'POST', body: JSON.stringify({...}), headers: {'Content-Type': 'application/json'}})`
   ajoute le jeton CSRF.
4. **Tables métier** : les déclarer dans `app/models.py` (ou `app/engine/models.py`, importé par
   `app/models.py`), puis `alembic revision --autogenerate -m "tables moteur"`.
5. **Tests** : compléter `tests/test_admin.py::test_moteur_seul` (moteur seul) et `test_moteur_page_et_api`.

> **Calculs longs** (plus de quelques secondes) : ne pas les exécuter dans la requête HTTP. Prévoir une file de
> tâches (table `jobs` + processus `worker` dans le compose, ou RQ / Celery avec Redis) et une page qui affiche
> l'état. Le squelette ne l'inclut pas.

## Ajouter une page protégée

```python
# app/engine/routes.py (ou un nouveau module inclus dans app/main.py)
@router.get("/rapports")
def rapports(request: Request, user: User = Depends(require_permission(perms.ENGINE_RUN))):
    return render(request, "engine/rapports.html", active="rapports", ...)
```

- Gabarit : `{% extends "shell.html" %}`, titre avec la macro `page_head` de `partials/ui.html`.
- Menu : ajouter un `NavItem` dans `NAV` (`app/web.py`), avec la même permission. Le menu masque l'entrée,
  mais seule la dépendance `require_permission` protège réellement la page.
- Formulaire POST : `<input type="hidden" name="csrf" value="{{ csrf_token }}">`.
- Nouvelle permission : l'ajouter à `CATALOG` dans `app/core/permissions.py`, puis la cocher dans
  **Administration › Rôles et permissions** (ou dans une migration si elle doit exister d'office).
- Action sensible : `audit.record(db, "module.action", actor=user, …)` et son libellé dans `ACTIONS`
  (`app/core/audit.py`).

## Conventions d'interface

- Interface, messages et e-mails **en français** ; dates `JJ/MM/AAAA` (filtres `date_fr`, `datetime_fr`),
  numéros de semaine ISO (`week` → `S48`).
- Listes : recherche **pendant la frappe**. Formulaire `GET` marqué `data-live-search`, zone
  `data-live-results`, rendue par la même route (voir `admin/users.html`).
- Exports : toujours **CSV et Excel** côte à côte, sur la liste filtrée (`csv_response` / `xlsx_response` de
  `app/core/exports.py`, macro `export_buttons`). CSV : séparateur `;`, BOM UTF-8.
- Action irréversible : `data-confirm="Ce qui va se passer…"` sur le formulaire.
- Charte : uniquement les variables `var(--color-*)` de `tokens.css`, et aucun `style="…"` ni `<script>` en
  ligne (la CSP les bloque).

## Pièges connus

| Piège | Explication |
|-------|-------------|
| `form.values` dans un gabarit | Jinja renvoie la méthode `dict.values`, pas la clé. Écrire `form.get('values')` (bug rencontré sur la page Moteur) |
| Style ou script en ligne sans effet | Bloqué par la CSP : passer par un fichier CSS / JS de `app/static/` |
| Lancement avec `uvicorn app.main:app` | Il n'y a pas de variable `app` : utiliser `uvicorn --factory app.main:create_app` |
| Toutes les connexions verrouillées en production | `FORWARDED_ALLOW_IPS` mal réglé : tout le monde a l'IP du proxy (02-deploiement) |
| Mot de passe MariaDB avec `@` ou `/` | Casse `DATABASE_URL` : lettres et chiffres uniquement |
