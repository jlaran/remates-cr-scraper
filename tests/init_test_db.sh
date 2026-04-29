#!/usr/bin/env bash
set -euo pipefail

CONTAINER=remates_test_pg
PORT=5499
DB_URL="postgresql://postgres:test@localhost:${PORT}/remates_test"
WEB_REPO="/Users/juanci/Documents/Development/Remates"

echo "▶ stopping any old container..."
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

echo "▶ launching postgis/postgis:16-3.4 on :${PORT}..."
docker run -d --name "$CONTAINER" \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=remates_test \
  -p "${PORT}:5432" postgis/postgis:16-3.4 >/dev/null

echo "▶ waiting for postgres to accept connections..."
for i in {1..30}; do
  if PGPASSWORD=test psql -h localhost -p "$PORT" -U postgres -d remates_test -c "SELECT 1" >/dev/null 2>&1; then
    echo "  ready"
    break
  fi
  sleep 1
done

# Apply migrations in order. Drizzle's 0000_*.sql may have a random word in the name.
INITIAL_SCHEMA=$(ls "$WEB_REPO"/apps/web/drizzle/migrations/0000_*.sql | head -1)
POSTGIS_SEEDS="$WEB_REPO/apps/web/drizzle/migrations/0001_postgis_and_seeds.sql"
FOR_SALE_KIND="$WEB_REPO/apps/web/drizzle/migrations/0002_add_for_sale_kind.sql"

echo "▶ applying $INITIAL_SCHEMA..."
psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$INITIAL_SCHEMA" >/dev/null

echo "▶ applying 0001_postgis_and_seeds.sql..."
psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$POSTGIS_SEEDS" >/dev/null

echo "▶ applying 0002_add_for_sale_kind.sql..."
psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$FOR_SALE_KIND" >/dev/null

echo "▶ done. DATABASE_URL=$DB_URL"
