# 04 · Intégrations

L'application ne dépend d'aucun service externe pour fonctionner : pas de CDN, pas de service de QR code,
pas de SSO. Deux intégrations seulement.

## Serveur SMTP

Utilisé uniquement pour envoyer le code de réinitialisation du mot de passe (`app/core/mailer.py`).

| À configurer côté application | À configurer côté serveur de courriel |
|-------------------------------|----------------------------------------|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Autoriser `SMTP_FROM` comme expéditeur (SPF/DKIM du domaine ; expéditeur vérifié chez Brevo, etc.) |

Comportement :

- `SMTP_HOST` vide : le message, code compris, est écrit dans `docker compose logs app`. Pratique en
  développement, **à ne pas laisser en production**.
- Échec d'envoi : l'utilisateur voit « L'e-mail n'a pas pu être envoyé. Contactez un administrateur. » et le
  code n'est pas enregistré. Le détail de l'erreur est dans les journaux (`Échec de l'envoi de l'e-mail à …`).

Test rapide depuis le conteneur :

```bash
docker compose exec app python -c "from app.config import get_settings; from app.core.mailer import send_mail; print(send_mail(get_settings(), 'vous@exemple.fr', 'Test', 'Bonjour'))"
```

## Applications d'authentification (2FA)

TOTP standard (RFC 6238, SHA-1, 6 chiffres, pas de 30 s, tolérance ±30 s) : Google Authenticator, Microsoft
Authenticator, FreeOTP, Bitwarden, 1Password… Le QR code est généré par l'application elle-même
(bibliothèque `qrcode`). Le secret ne quitte donc jamais le serveur, sauf pour être affiché à l'utilisateur.

Le libellé affiché dans l'application du téléphone est `APP_NAME` suivi de l'identifiant.

> Les codes dépendent de l'heure : si les codes sont refusés pour tout le monde, vérifier l'horloge du serveur
> (`date -u` sur l'hôte).
