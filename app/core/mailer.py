"""Envoi d'e-mails par SMTP. Sans SMTP_HOST, le message est écrit dans le journal (développement)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import Settings

log = logging.getLogger(__name__)


def send_mail(settings: Settings, to: str, subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if not settings.smtp_host:
        log.warning("SMTP non configuré : e-mail non envoyé.\nÀ : %s\nObjet : %s\n\n%s", to, subject, body)
        return True

    try:
        context = ssl.create_default_context()
        if settings.smtp_security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=15)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
            if settings.smtp_security == "starttls":
                server.starttls(context=context)
        with server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        log.exception("Échec de l'envoi de l'e-mail à %s", to)
        return False
