#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${MIGRATION_DATABASE_URL:-}" ]]; then
  echo "MIGRATION_DATABASE_URL is required for the release job" >&2
  exit 1
fi
export DATABASE_URL="$MIGRATION_DATABASE_URL"
cd "$(dirname "$0")/wizdesk_backend"
python manage.py check_production_config
python manage.py migrate --noinput
