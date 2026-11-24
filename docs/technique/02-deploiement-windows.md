# 02 bis · Déploiement sur Windows (sans Docker)

Mode opératoire à suivre dans l'ordre. Valeurs d'exemple : dossier `C:\apps\pyapp`, serveur `srv-app`.

> Ce que les scripts appellent (`init-env`, migrations, `app.serve` en HTTP et en HTTPS, sauvegarde) a été
> testé. Les fichiers `.bat` eux-mêmes n'ont pas encore été exécutés sur un vrai Windows : noter ici tout
> écart constaté lors de la première installation.

## Principe

Trois scripts dans `windows\`, qui appellent Python :

| Script | Rôle |
|--------|------|
| `install.bat` | Vérifie Python, crée l'environnement `.venv`, installe les dépendances, crée `.env` au premier passage, met à jour la base. À relancer après chaque mise à jour du code |
| `start.bat` | Lance l'application (`python -m app.serve`) avec les réglages de `.env` : adresse, port, HTTPS |
| `backup.bat` | Sauvegarde la base sans arrêter l'application ; garde 30 jours de sauvegardes |

Base de données : un fichier SQLite, `data\app.db`. Il n'y a pas de serveur de base à installer.

## Prérequis

| Logiciel | Où le trouver | Remarque |
|----------|---------------|----------|
| Windows 10/11 ou Windows Server 2019+ | | |
| Python 3.12 ou plus (3.13 conseillé), 64 bits | https://www.python.org/downloads/windows/ | Cocher **Add python.exe to PATH** à l'installation. Pour un démarrage automatique (étape 5), choisir aussi **Install for all users** |
| Accès Internet au moment de l'installation | | Pour télécharger les dépendances Python (pip) |

Vérifier dans une **nouvelle** invite de commandes : `python --version` doit afficher `Python 3.12` ou plus.
Si la Boutique Microsoft s'ouvre à la place, désactiver les alias `python.exe` dans *Paramètres › Applications
› Alias d'exécution d'application*.

## 1. Installer

Copier le projet dans `C:\apps\pyapp` (`git clone`, ou décompresser l'archive), puis double-cliquer
`windows\install.bat`, ou dans une invite de commandes :

```bat
cd /d C:\apps\pyapp
windows\install.bat
```

Fin attendue :

```
.env créé : vérifier APP_NAME, APP_SHORT, ORG_NAME, SERVER_PORT et SMTP_*.
Migrations de la base ...
Installation terminee.
```

## 2. Régler `.env`

Ouvrir `C:\apps\pyapp\.env` avec le Bloc-notes. `SECRET_KEY` et `DATABASE_URL` sont déjà remplis.

| Variable | À mettre |
|----------|----------|
| `APP_NAME`, `APP_SHORT`, `ORG_NAME` | Nom de l'application, sigle, organisation |
| `SERVER_HOST` | `0.0.0.0` : accessible depuis le réseau (défaut) ; `127.0.0.1` : depuis le serveur seulement |
| `SERVER_PORT` | Port d'écoute (défaut `8095`) |
| `SSL_CERTFILE`, `SSL_KEYFILE` | Facultatif : HTTPS, voir l'étape 4 |
| `SMTP_*` | Serveur de courriel, pour les codes de mot de passe oublié |

Les variables `DB_*`, `WEB_PUBLISH_*` et `MARIADB_*` ne servent qu'à Docker : les ignorer.

## 3. Lancer et créer l'administrateur

Double-cliquer `windows\start.bat`. La fenêtre affiche :

```
Python App Starter : http://localhost:8095  (Ctrl+C pour arrêter)
INFO:     Uvicorn running on http://0.0.0.0:8095 (Press CTRL+C to quit)
```

Ouvrir `http://localhost:8095` sur le serveur : la page **Première configuration** demande l'identifiant, le
courriel et le mot de passe de l'administrateur.

> Faire cette étape **avant** d'ouvrir l'accès aux autres postes : tant qu'aucun compte n'existe, la première
> personne qui ouvre la page devient administrateur.

L'application tourne tant que la fenêtre reste ouverte.

Accès depuis les autres postes (`http://srv-app:8095`) : autoriser le port dans le pare-feu Windows, en
invite de commandes **administrateur** :

```bat
netsh advfirewall firewall add rule name="pyapp" dir=in action=allow protocol=TCP localport=8095
```

## 4. HTTPS (facultatif, conseillé)

En HTTP, les mots de passe circulent en clair sur le réseau. Pour activer le HTTPS, il faut un certificat au
format **PEM** : un fichier pour le certificat, un autre pour la clé privée.

1. Obtenir le certificat (autorité interne, service informatique). S'il est livré en `.pfx`, le convertir
   avec OpenSSL :
   ```bat
   openssl pkcs12 -in certificat.pfx -clcerts -nokeys -out cert.pem
   openssl pkcs12 -in certificat.pfx -nocerts -nodes -out key.pem
   ```
2. Copier `cert.pem` et `key.pem` dans `C:\apps\pyapp\certs\`. Ce dossier ne doit être lisible que par les
   administrateurs, car `key.pem` est la clé privée.
3. Dans `.env` (barres obliques `/`) :
   ```
   SSL_CERTFILE=C:/apps/pyapp/certs/cert.pem
   SSL_KEYFILE=C:/apps/pyapp/certs/key.pem
   SERVER_PORT=443
   ```
4. Relancer `start.bat` : l'adresse devient `https://srv-app` (le cookie de session passe automatiquement en
   `Secure`). Adapter la règle de pare-feu au port choisi.

## 5. Démarrage automatique (facultatif)

Pour que l'application démarre avec le serveur, sans session ouverte, créer une tâche planifiée, en invite de
commandes **administrateur** :

```bat
schtasks /Create /TN "pyapp" /SC ONSTART /DELAY 0001:00 /RU SYSTEM /RL HIGHEST /TR "\"C:\apps\pyapp\windows\start.bat\" /nopause"
schtasks /Run /TN "pyapp"
```

| Action | Commande |
|--------|----------|
| Arrêter | `schtasks /End /TN "pyapp"` |
| Démarrer | `schtasks /Run /TN "pyapp"` |
| Supprimer la tâche | `schtasks /Delete /TN "pyapp" /F` |

> Python doit être installé « pour tous les utilisateurs » : la tâche tourne sous le compte système.
> Dans *Planificateur de tâches › pyapp › Propriétés › Paramètres*, décocher « Arrêter la tâche si elle
> s'exécute plus de 3 jours », réglage actif par défaut.

## 6. Planifier la sauvegarde

```bat
schtasks /Create /TN "pyapp - sauvegarde" /SC DAILY /ST 02:00 /RU SYSTEM /TR "C:\apps\pyapp\windows\backup.bat"
schtasks /Run /TN "pyapp - sauvegarde"
```

L'essai doit créer `C:\apps\pyapp\backups\app-AAAA-MM-JJ_HHMM.db`. **Copier le dossier `backups\` hors du
serveur** (partage réseau, outil de sauvegarde), ainsi que le fichier `.env`.

## Recette

| Vérification | Attendu |
|--------------|---------|
| `http://localhost:8095/health` sur le serveur | `{"status":"ok"}` |
| `http://srv-app:8095` depuis un poste (ou `https://…` à l'étape 4) | Page de connexion |
| Connexion, puis **Administration › Journal d'audit** | Colonne « Adresse IP » = IP du poste |
| `windows\backup.bat` | Nouveau fichier dans `backups\` |
| Redémarrage du serveur (si étape 5) | L'application revient seule, environ 1 min après le démarrage |

## Mise à jour

1. Sauvegarder : `windows\backup.bat`.
2. Arrêter l'application : fermer la fenêtre de `start.bat`, ou `schtasks /End /TN "pyapp"`.
3. Remplacer le code (`git pull`, ou copie des nouveaux fichiers en **gardant** `.env`, `data\`, `backups\`,
   `certs\`).
4. `windows\install.bat` : met à jour les dépendances et la base, et conserve `.env`.
5. Relancer `start.bat`, ou `schtasks /Run /TN "pyapp"`.

## Restauration

1. Arrêter l'application.
2. Supprimer `data\app.db-wal` et `data\app.db-shm` s'ils existent.
3. Copier la sauvegarde voulue sur `data\app.db` :
   ```bat
   copy /Y backups\app-AAAA-MM-JJ_HHMM.db data\app.db
   ```
4. Relancer l'application.

## Option : MariaDB au lieu de SQLite

SQLite convient à un outil interne (quelques dizaines d'utilisateurs simultanés). Pour utiliser une base
MariaDB existante : créer la base et le compte (`CHARACTER SET utf8mb4`), puis dans `.env`
`DATABASE_URL=mysql+pymysql://pyapp:MotDePasse@serveur-db:3306/pyapp?charset=utf8mb4` (mot de passe en lettres
et chiffres), et relancer `install.bat`. La sauvegarde se fait alors avec `mariadb-dump`, pas `backup.bat`.

## Dépannage

| Symptôme | Cause probable | Que faire |
|----------|----------------|-----------|
| `Python 3.12 ou plus est introuvable dans le PATH` | Python absent, trop ancien, ou installé sans « Add to PATH » | Réinstaller en cochant l'option, puis ouvrir une **nouvelle** invite de commandes |
| La Boutique Microsoft s'ouvre | Alias d'exécution `python.exe` de Windows | Le désactiver (voir Prérequis) |
| Erreur pendant « Installation des dependances » | Pas d'accès Internet ou proxy d'entreprise | `set HTTPS_PROXY=http://proxy:3128` avant `install.bat` |
| `[Errno 10048]` au lancement | Port déjà utilisé | `netstat -ano \| findstr :8095` ; changer `SERVER_PORT` |
| La fenêtre se ferme aussitôt (tâche planifiée) | Erreur au démarrage | Lancer `start.bat` à la main pour lire le message |
| `Fichier de certificat introuvable` | Chemin `SSL_CERTFILE` / `SSL_KEYFILE` faux | Chemin complet avec des `/` |
| Les postes n'accèdent pas à l'application | Pare-feu, ou `SERVER_HOST=127.0.0.1` | Règle `netsh` de l'étape 3 ; `SERVER_HOST=0.0.0.0` |
| Déconnecté juste après la connexion | `COOKIE_SECURE=true` alors que le site est en HTTP | Laisser `COOKIE_SECURE=auto` |
| `database is locked` | Fichier de base copié à la main pendant l'activité | Utiliser `backup.bat` |

Les autres symptômes (2FA, SMTP, page expirée) sont décrits dans [08 · Exploitation](08-exploitation.md#dépannage).
