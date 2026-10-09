#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r requirements.txt
cd wizdesk_backend
python manage.py collectstatic --noinput
