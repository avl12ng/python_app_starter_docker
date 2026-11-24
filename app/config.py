"""Configuration lue dans les variables d'environnement (ou le fichier .env)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # hide_input_in_errors : une valeur invalide (secret, mot de passe) n'est jamais recopiée dans les journaux
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    # Identité affichée dans l'interface (barre latérale, titres, e-mails, application 2FA)
    app_name: str = "Application"
    app_short: str = "APP"
    org_name: str = "Organisation"
    timezone: str = "Europe/Paris"
    debug: bool = False

    # Secret utilisé pour signer les codes de réinitialisation. Obligatoire, 32 caractères minimum.
    secret_key: str = Field(min_length=32)

    # mysql+pymysql://user:pass@host:3306/base?charset=utf8mb4  ou  sqlite:///./data/app.db
    database_url: str = "sqlite:///./data/app.db"

    # Session côté serveur (table web_sessions) : le cookie ne contient qu'un jeton aléatoire.
    session_cookie: str = "app_session"
    session_idle_minutes: int = Field(default=120, ge=5, le=1440)
    # auto : cookie Secure dès que la requête arrive en HTTPS (y compris derrière un proxy de confiance)
    cookie_secure: Literal["auto", "true", "false"] = "auto"

    # Anti force brute (fenêtre glissante de lockout_minutes)
    login_max_failed_account: int = Field(default=8, ge=1)
    login_max_failed_per_ip_user: int = Field(default=12, ge=1)
    login_max_failed_per_ip: int = Field(default=40, ge=1)
    login_max_failed_totp: int = Field(default=6, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)

    # Mot de passe oublié
    reset_ttl_minutes: int = Field(default=10, ge=1, le=60)
    reset_max_per_ip_hour: int = Field(default=15, ge=1, le=100)

    # SMTP : si smtp_host est vide, les e-mails sont écrits dans le journal (mode développement).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@example.local"

    # Serveur web lancé par `python -m app.serve` (Windows / sans Docker). Sous Docker, voir docker-compose.yml.
    server_host: str = "0.0.0.0"  # noqa: S104 - écoute réseau voulue (pas de reverse-proxy)
    server_port: int = Field(default=8095, ge=1, le=65535)
    web_workers: int = Field(default=1, ge=1, le=16)
    forwarded_allow_ips: str = "127.0.0.1"
    # HTTPS direct par uvicorn : chemins des fichiers PEM du certificat et de sa clé (vides = HTTP)
    ssl_certfile: str = ""
    ssl_keyfile: str = ""

    # Journal d'audit
    audit_retention_days: int = Field(default=365, ge=30)

    @field_validator("secret_key")
    @classmethod
    def _secret_not_placeholder(cls, value: str) -> str:
        if "change-me" in value.lower():
            raise ValueError("SECRET_KEY doit être remplacé par une valeur aléatoire (voir README).")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
