"""Fail a release when essential pilot security settings are missing."""

import os
from email.utils import parseaddr
from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import run_checks
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Validate the production database, HTTPS, and email configuration."

    def handle(self, *args, **options):
        failures = []
        database = settings.DATABASES["default"]
        if settings.DEBUG:
            failures.append("DEBUG must be False")
        if database["ENGINE"] != "django.db.backends.postgresql":
            failures.append("DATABASE_URL must use PostgreSQL")
        if (not settings.SECRET_KEY or len(settings.SECRET_KEY) < 50
                or settings.SECRET_KEY.startswith(("replace-", "collectstatic-"))):
            failures.append("SECRET_KEY must contain at least 50 characters")
        ci_local_hosts = os.getenv("CI", "").lower() == "true"
        if not settings.ALLOWED_HOSTS or any(
            "*" in host or (host in ("localhost", "127.0.0.1") and not ci_local_hosts)
            for host in settings.ALLOWED_HOSTS
        ):
            failures.append("ALLOWED_HOSTS must name only production hosts")
        if not settings.CSRF_TRUSTED_ORIGINS or any(
            urlsplit(origin).scheme != "https" or not urlsplit(origin).hostname
            or "*" in origin
            for origin in settings.CSRF_TRUSTED_ORIGINS
        ):
            failures.append("CSRF_TRUSTED_ORIGINS must use HTTPS")
        frontend = urlsplit(settings.FRONTEND_URL)
        if (frontend.scheme != "https" or not frontend.hostname
                or frontend.hostname not in settings.ALLOWED_HOSTS
                or frontend.path not in ("", "/") or frontend.query or frontend.fragment
                or frontend.username or frontend.password):
            failures.append("FRONTEND_URL must be an allowed HTTPS origin")
        elif f"https://{frontend.netloc}" not in settings.CSRF_TRUSTED_ORIGINS:
            failures.append("CSRF_TRUSTED_ORIGINS must include FRONTEND_URL")
        if not settings.SECURE_SSL_REDIRECT:
            failures.append("SECURE_SSL_REDIRECT must be True")
        if not settings.SESSION_COOKIE_SECURE:
            failures.append("SESSION_COOKIE_SECURE must be True")
        if not settings.CSRF_COOKIE_SECURE:
            failures.append("CSRF_COOKIE_SECURE must be True")
        if settings.SECURE_HSTS_SECONDS < 31536000:
            failures.append("SECURE_HSTS_SECONDS must be at least 31536000")
        if settings.CORS_ALLOW_ALL_ORIGINS:
            failures.append("CORS_ALLOW_ALL_ORIGINS must be False")
        if not settings.EMAIL_VERIFICATION_REQUIRED:
            failures.append("EMAIL_VERIFICATION_REQUIRED must be True")
        if settings.EMAIL_BACKEND != "anymail.backends.resend.EmailBackend":
            failures.append("EMAIL_BACKEND must use the Resend API backend")
        if not settings.ANYMAIL.get("RESEND_API_KEY"):
            failures.append("RESEND_API_KEY must be configured")
        sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
        if not sender or "@" not in sender or sender.endswith(".local"):
            failures.append("DEFAULT_FROM_EMAIL must name a sender")
        if int(os.getenv("WEB_CONCURRENCY", "2")) > 1 and settings.CACHES["default"][
            "BACKEND"
        ].endswith("LocMemCache"):
            failures.append("Multiple workers require a shared cache")
        # Django recommends preload and subdomain HSTS globally. The pilot's
        # shared Render hostname intentionally uses neither; all other
        # deployment warnings remain release failures.
        accepted_hsts = {"security.W005", "security.W021"}
        warnings = run_checks(include_deployment_checks=True)
        unexpected = [item.id for item in warnings if item.id not in accepted_hsts]
        if unexpected:
            failures.append("Django deployment checks: " + ", ".join(sorted(set(unexpected))))
        if failures:
            raise CommandError("Production configuration failed: " + "; ".join(failures))
        expected = sorted({item.id for item in warnings if item.id in accepted_hsts})
        if expected:
            self.stdout.write("Conservative HSTS policy: " + ", ".join(expected))
        self.stdout.write(self.style.SUCCESS("Production configuration passed"))
