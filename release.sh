#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/wizdesk_backend"
python manage.py migrate --noinput
