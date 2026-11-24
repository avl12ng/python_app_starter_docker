#!/bin/sh
# Démarrage du conteneur : attente de la base, migrations, administrateur INITIAL_ADMIN_* (facultatif), puis la commande.
set -e

echo "Attente de la base de données…"
python - <<'PY'
import sys, time
from sqlalchemy import create_engine, text
from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
for attempt in range(60):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        last = exc
        time.sleep(2)
print(f"Base de données injoignable : {last}", file=sys.stderr)
sys.exit(1)
PY

echo "Migrations…"
alembic upgrade head

python -m app.cli ensure-admin

exec "$@"
