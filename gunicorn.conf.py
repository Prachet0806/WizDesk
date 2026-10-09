# Gunicorn configuration for WizDesk
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
backlog = 2048

# Worker processes
workers = int(os.getenv('WEB_CONCURRENCY', '2'))
worker_class = 'sync'
worker_connections = 1000
timeout = 120
keepalive = 2

# Restart workers after this many requests (prevents memory leaks)
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'wizdesk'

# Security
limit_request_fields = 100
limit_request_field_size = 8190
limit_request_line = 4094

# Performance
preload_app = True

# Post-fork: close old database connections to avoid issues with preload_app + Django
def post_fork(server, worker):
    import django
    from django.db import connections
    for conn in connections.all():
        conn.close_if_unusable_or_obsolete()