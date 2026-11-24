"""Lance le serveur web avec les réglages de .env : `python -m app.serve`.

Utilisé par windows\\start.bat (et utilisable sur tout système sans Docker). Applique d'abord les
migrations de la base, comme le conteneur Docker au démarrage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[1]


def migrate() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")


def main() -> None:
    settings = get_settings()
    migrate()
    ssl = {}
    if settings.ssl_certfile or settings.ssl_keyfile:
        for path in (settings.ssl_certfile, settings.ssl_keyfile):
            if not Path(path).is_file():
                sys.exit(f"Fichier de certificat introuvable : {path!r} (SSL_CERTFILE / SSL_KEYFILE dans .env)")
        ssl = {"ssl_certfile": settings.ssl_certfile, "ssl_keyfile": settings.ssl_keyfile}
    scheme = "https" if ssl else "http"
    shown = "localhost" if settings.server_host in ("0.0.0.0", "127.0.0.1") else settings.server_host  # noqa: S104
    print(f"{settings.app_name} : {scheme}://{shown}:{settings.server_port}  (Ctrl+C pour arrêter)")
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.server_host,
        port=settings.server_port,
        workers=settings.web_workers,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        server_header=False,
        **ssl,
    )


if __name__ == "__main__":
    main()
