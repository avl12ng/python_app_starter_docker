# 06 · Règles de sécurité

Règles reprises de *secure_website_starter* (PHP), avec les écarts signalés. Chacune est couverte par un test
dans `tests/`.

## Mots de passe

- 12 caractères minimum, avec une majuscule, une minuscule, un chiffre et un caractère spécial
  (`app/core/passwords.py`). Les règles se cochent pendant la frappe dans les formulaires.
- Hachage **Argon2id**, rehaché automatiquement à la connexion si les paramètres évoluent.
  *Écart* : le PHP utilisait `password_hash` (bcrypt). Les comptes ne sont pas repris : pas de migration de hash.
- Un nouveau mot de passe doit différer de l'ancien.
- Changer son mot de passe déconnecte les **autres** sessions du compte. Une réinitialisation, ou un changement
  fait par un administrateur, déconnecte **toutes** ses sessions.

## Connexion et verrouillage

- Message identique pour un compte inconnu, un mauvais mot de passe ou un compte désactivé (« Identifiant ou
  mot de passe incorrect »). Pour un compte inconnu, un hachage factice est vérifié, si bien que la réponse
  prend autant de temps.
- Trois compteurs d'échecs sur une fenêtre glissante de `LOGIN_LOCKOUT_MINUTES` : par compte (8), par couple
  compte + IP (12), par IP (40). Au-delà, la connexion est refusée avec le temps d'attente restant, même avec
  le bon mot de passe. Les codes 2FA faux comptent aussi (6 par compte).
- L'identifiant de session est renouvelé à la connexion (protection contre la fixation de session) et le
  jeton CSRF change.
- Après connexion, seule une redirection vers un chemin local est acceptée (`next=/admin`, jamais
  `//site` ou `https://…`).

## Double authentification

- Après le mot de passe, le compte n'est pas encore connecté : une étape « Code de vérification » valable
  5 minutes.
- Un code déjà utilisé est refusé (`totp_last_step`). *Ajout* par rapport au PHP.
- L'activation se fait en deux temps (QR code, puis code de confirmation, valable 10 minutes). La désactivation
  demande le mot de passe actuel (*ajout*).
- Un administrateur peut réinitialiser la 2FA d'un compte (téléphone perdu) depuis sa fiche.

## Mot de passe oublié

- Code à 10 chiffres, valable `RESET_TTL_MINUTES` (10), envoyé par courriel. Une nouvelle demande annule les
  codes précédents.
- Même message que le compte existe ou non.
- `RESET_MAX_PER_IP_HOUR` (15) par IP et par heure, pour les demandes **et** les codes faux, ce qui empêche
  d'essayer les codes en masse. *Ajout* : le PHP ne limitait que les demandes.
- Le code est stocké sous forme d'empreinte HMAC-SHA256 avec `SECRET_KEY`. Le PHP utilisait un SHA-256 sans clé.

## Sessions et HTTP

- Session stockée en base, cookie `HttpOnly`, `SameSite=Lax`, `Secure` en HTTPS, expiration après
  `SESSION_IDLE_MINUTES` d'inactivité.
- L'utilisateur est relu à chaque requête : désactiver un compte le déconnecte immédiatement.
- CSRF : jeton par session, obligatoire sur tout envoi (formulaire : champ `csrf` ; JavaScript : en-tête
  `X-CSRF-Token`, voir `window.appFetch` dans `app.js`).
- En-têtes : CSP stricte (`script-src 'self'`, `style-src 'self'`, `frame-ancestors 'none'`), `nosniff`,
  `Referrer-Policy`, `Permissions-Policy`, HSTS en HTTPS, `Cache-Control: no-store` sur les pages.

## Première configuration

- Tant que la table `users` est vide, `/login` redirige vers `/setup`, qui crée un compte **administrateur**
  (mêmes règles de mot de passe), le connecte et l'invite à activer la 2FA.
- Dès qu'un compte existe, `/setup` redirige vers la connexion, y compris pour un envoi direct du formulaire.
  La création verrouille la ligne du rôle `admin` : deux envois simultanés ne créent pas deux comptes.
- Risque assumé : sur une instance neuve exposée, la première personne arrivée devient administrateur.
  D'où la consigne de faire cette étape avant d'ouvrir l'accès (02-deploiement).

## Administration

- Les permissions sont vérifiées côté serveur sur chaque route (`require_permission`), en plus du menu.
- On ne peut pas désactiver, changer de rôle ni supprimer **son propre** compte.
- Le **dernier administrateur actif** ne peut être ni désactivé, ni rétrogradé, ni supprimé.
- Le rôle `admin` garde toujours `admin.access`, `users.manage` et `roles.manage` (cases verrouillées).
- Un rôle attribué à des comptes ne peut pas être supprimé.

## Journal d'audit

Connexions (réussies, échouées), déconnexions, demandes et réinitialisations de mot de passe, changements de
courriel, de mot de passe et de 2FA, création, modification et suppression de comptes et de rôles, calculs du
moteur. Conservation : `AUDIT_RETENTION_DAYS` (365 jours).

## Non repris de secure_website_starter

| Fonction PHP | Pourquoi |
|--------------|----------|
| Configuration serveur depuis l'interface (`admin_server.php`) | La configuration passe par `.env` : modifiable sans accès web, sans fichier de secrets inscriptible par l'application |
| Gestion BDD depuis l'interface (migrations, import/export) | Remplacée par Alembic au démarrage et par les commandes de sauvegarde (08-exploitation) |
| Bascule FR / EN | Interface en français uniquement (convention des outils internes) |
