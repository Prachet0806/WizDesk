#!/usr/bin/env bash
set -euo pipefail

# Validate settings and apply repeatable migrations using Neon's direct URL.
/app/release.sh

# release.sh runs in a child process, so this process retains the pooled URL.
cd /app/wizdesk_backend
exec gunicorn --config /app/gunicorn.conf.py wizdesk_backend.wsgi:application
