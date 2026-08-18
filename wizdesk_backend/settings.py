"""
Stale duplicate of the canonical settings package.
The canonical configuration lives in `wizdesk_backend.wizdesk_backend.settings`
and is what `wizdesk_backend/manage.py` (and the build/deploy scripts) use.
This module only exists so that tooling running from the repository root
(e.g. `gunicorn wizdesk_backend.wsgi:application`) resolves to the same config.
"""
from wizdesk_backend.wizdesk_backend.settings import *