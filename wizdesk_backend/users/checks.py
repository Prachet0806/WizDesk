import os

from django.conf import settings
from django.core.checks import Warning, register


@register(deploy=True)
def shared_throttle_cache(app_configs, **kwargs):
    backend = settings.CACHES["default"]["BACKEND"]
    if int(os.getenv("WEB_CONCURRENCY", "2")) > 1 and backend.endswith("LocMemCache"):
        return [
            Warning(
                "Multiple workers require a shared throttle cache. Configure CACHE_URL or use WEB_CONCURRENCY=1.",
                id="wizdesk.W001",
            )
        ]
    return []


@register(deploy=True)
def production_email_delivery(app_configs, **kwargs):
    if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
        return [
            Warning(
                "Password recovery needs a private email backend; console delivery can expose reset links in logs.",
                id="wizdesk.W002",
            )
        ]
    return []
