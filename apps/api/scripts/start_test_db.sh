#!/usr/bin/env bash
set -euo pipefail

PORT=5433
DATA_DIR="/tmp/filament_pg_test_16"
LOG_FILE="${DATA_DIR}/postgres.log"

if [ ! -d "${DATA_DIR}" ]; then
    echo "Initializing temporary PostgreSQL cluster at ${DATA_DIR}..."
    initdb -D "${DATA_DIR}" -U postgres -A trust
fi

if /opt/homebrew/bin/pg_isready -p "${PORT}" -h 127.0.0.1 >/dev/null 2>&1; then
    echo "PostgreSQL is already running on port ${PORT}."
else
    echo "Starting PostgreSQL on port ${PORT}..."
    /opt/homebrew/bin/pg_ctl -D "${DATA_DIR}" -l "${LOG_FILE}" -o "-p ${PORT} -k /tmp" start
    sleep 1
fi

if ! /opt/homebrew/bin/psql -p "${PORT}" -h 127.0.0.1 -U postgres -lqt | cut -d \| -f 1 | grep -qw filament_test; then
    echo "Creating filament_test database..."
    /opt/homebrew/bin/createdb -p "${PORT}" -h 127.0.0.1 -U postgres filament_test
    echo "Running migrations..."
    (cd "$(dirname "$0")/.." && DATABASE_URL="postgresql+asyncpg://postgres@127.0.0.1:${PORT}/filament_test" .venv/bin/alembic upgrade head)
fi

echo "PostgreSQL test cluster ready on port ${PORT}."

