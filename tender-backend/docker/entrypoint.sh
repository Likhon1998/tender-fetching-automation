#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PY'
import asyncio
import os
import sys

async def wait():
    import asyncpg
    host = os.getenv("DB_HOST", "db")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    database = os.getenv("DB_NAME", "tender-fetching")
    for attempt in range(40):
        try:
            conn = await asyncpg.connect(
                host=host, port=port, user=user, password=password, database=database
            )
            await conn.close()
            print("Database is ready.")
            return
        except Exception as exc:
            print(f"DB not ready ({attempt + 1}/40): {exc}")
            await asyncio.sleep(2)
    print("Database did not become ready in time.", file=sys.stderr)
    sys.exit(1)

asyncio.run(wait())
PY

echo "Running migrations..."
alembic upgrade head

if [ "${RUN_SEEDS:-true}" = "true" ]; then
  echo "Seeding admin and reference data (safe to re-run)..."
  python -m scripts.seed_admin || true
  python -m scripts.seed_reference_data || true
fi

exec "$@"
