#!/usr/bin/env bash
# exit on error
set -o errexit
set -o pipefail
set -o nounset

# Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# Collect static files
cd wizdesk_backend
python manage.py collectstatic --no-input

# Run migrations (Render runs this on every deploy)
python manage.py migrate --no-input
