# Documentation technique

Pour le développeur ou l'exploitant qui reprend le projet. Rien ici ne suppose d'avoir suivi son histoire.

## L'essentiel en une page

- **Quoi** : squelette d'application web Python (FastAPI). L'authentification complète est prête, et un module
  `app/engine/` attend le moteur métier.
- **Origine** : l'authentification est un portage en Python de *secure_website_starter* (PHP) : mêmes règles
  de mot de passe, de verrouillage, de 2FA et de réinitialisation. La charte graphique est celle de
  *digitization_commercial* : palette, police Hanken Grotesk, fond géométrique, coque avec barre latérale.
- **Où ça tourne** : soit deux conteneurs, `app` (uvicorn) et `db` (MariaDB 11.8), décrits par `docker-compose.yml` ;
  soit, sans Docker, Python lancé par des scripts `.bat` avec une base SQLite (dossier `windows/`).
- **Démarrage** : le conteneur attend la base, applique les migrations Alembic, puis lance uvicorn.
  Tant qu'aucun compte n'existe, l'interface affiche la page **Première configuration** pour créer
  l'administrateur.
- **Ce qui ne doit jamais se perdre** : le fichier `.env` (en particulier `SECRET_KEY`) et le volume
  `pyapp_db_data`.

## Sommaire

| Chapitre | Contenu |
|----------|---------|
| [01 · Architecture](01-architecture.md) | Schéma, conteneurs, organisation du code, cycle d'une requête |
| [02 · Déploiement](02-deploiement.md) | Mode opératoire Docker : installation, reverse-proxy HTTPS, mise à jour, retour arrière, recette |
| [02 bis · Windows](02-deploiement-windows.md) | Mode opératoire sans Docker : scripts `.bat`, HTTPS direct, démarrage automatique, sauvegarde planifiée |
| [03 · Configuration](03-configuration.md) | Toutes les variables du `.env` |
| [04 · Intégrations](04-integrations.md) | SMTP, applications d'authentification |
| [05 · Données](05-donnees.md) | Schéma, rôle de chaque table, migrations |
| [06 · Règles de sécurité](06-regles-securite.md) | Règles d'authentification, précises et testées |
| [07 · Développement](07-developpement.md) | Environnement local, tests, CI, brancher le moteur, ajouter une page, pièges |
| [08 · Exploitation](08-exploitation.md) | Supervision, journaux, sauvegarde et restauration, dépannage |

## Historique

| Version | Contenu |
|---------|---------|
| 0.1.0 | Squelette initial : authentification, 2FA, administration, journal d'audit, moteur d'exemple |

## Règle de mise à jour

À chaque évolution, **dans le même commit** : la page technique concernée, le README si c'est visible de
l'extérieur, la version et l'historique (`app/__init__.py`, `CHANGELOG` dans `app/admin/routes.py`, tableau
ci-dessus). Quand les écrans métier existeront, ajouter un mode d'emploi par profil (`docs/mode-emploi.md`,
servi aussi par une page Aide dans l'outil).
