#!/usr/bin/env bash
set -e
# run migrations only if flagged (avoids slowing tests)
if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
  alembic upgrade head
fi
exec "$@"
