import json
import os
import subprocess
import sys

from django.test import SimpleTestCase


class NorthflankSettingsTests(SimpleTestCase):
    def test_console_email_backend_is_a_deployment_warning(self):
        from django.test import override_settings

        from users.checks import production_email_delivery

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
        ):
            self.assertEqual(production_email_delivery(None)[0].id, "wizdesk.W002")

    def test_service_url_normalizes_allowed_host_and_verification_origin(self):
        for service_url in (
            "https://wizdesk.sandbox.northflank.app/",
            "wizdesk.sandbox.northflank.app",
        ):
            with self.subTest(service_url=service_url):
                env = os.environ.copy()
                env.update(
                    SECRET_KEY="test-only-key-for-settings-subprocess-0123456789",
                    DATABASE_URL="sqlite:///:memory:",
                    NORTHFLANK_SERVICE_URL=service_url,
                )
                env.pop("FRONTEND_URL", None)
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "import json; from wizdesk_backend import settings; "
                        "print(json.dumps([settings.FRONTEND_URL, settings.ALLOWED_HOSTS]))",
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                origin, hosts = json.loads(result.stdout)
                self.assertEqual(origin, "https://wizdesk.sandbox.northflank.app")
                self.assertIn("wizdesk.sandbox.northflank.app", hosts)
