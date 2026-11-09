import json
import os
import subprocess
import sys

from django.test import SimpleTestCase


class DeploymentSettingsTests(SimpleTestCase):
    def test_console_email_backend_is_a_deployment_warning(self):
        from django.test import override_settings

        from users.checks import production_email_delivery

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
        ):
            self.assertEqual(production_email_delivery(None)[0].id, "wizdesk.W002")

    def test_service_url_normalizes_allowed_host_and_verification_origin(self):
        for service_url in (
            "https://wizdesk.onrender.com/",
            "wizdesk.onrender.com",
        ):
            with self.subTest(service_url=service_url):
                env = os.environ.copy()
                env.update(
                    SECRET_KEY="test-only-key-for-settings-subprocess-0123456789",
                    DATABASE_URL="sqlite:///:memory:",
                    DEBUG="True",
                    RENDER_EXTERNAL_HOSTNAME=service_url,
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
                self.assertEqual(origin, "https://wizdesk.onrender.com")
                self.assertIn("wizdesk.onrender.com", hosts)

    def test_production_requires_postgresql_url(self):
        for database_url in (None, "sqlite:///:memory:"):
            with self.subTest(database_url=database_url):
                env = os.environ.copy()
                env["DEBUG"] = "False"
                env["SECRET_KEY"] = "test-only-key-for-settings-subprocess-0123456789"
                if database_url is None:
                    env["DATABASE_URL"] = ""
                else:
                    env["DATABASE_URL"] = database_url
                result = subprocess.run(
                    [sys.executable, "-c", "from wizdesk_backend import settings"],
                    env=env, capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DATABASE_URL", result.stderr)

    def test_postgresql_pooler_settings_and_release_validation(self):
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "wizdesk_backend.settings"
        env.update(
            DEBUG="False",
            SECRET_KEY="test-only-key-for-settings-subprocess-0123456789-long-enough",
            DATABASE_URL="postgresql://tester:password@localhost:55432/wizdesk",
            ALLOWED_HOSTS="wizdesk.example.com",
            CSRF_TRUSTED_ORIGINS="https://wizdesk.example.com",
            FRONTEND_URL="https://wizdesk.example.com",
            SECURE_SSL_REDIRECT="True",
            SESSION_COOKIE_SECURE="True",
            CSRF_COOKIE_SECURE="True",
            SECURE_HSTS_SECONDS="31536000",
            SECURE_HSTS_INCLUDE_SUBDOMAINS="False",
            SECURE_HSTS_PRELOAD="False",
            EMAIL_VERIFICATION_REQUIRED="True",
            EMAIL_BACKEND="anymail.backends.resend.EmailBackend",
            RESEND_API_KEY="test-only",
            DEFAULT_FROM_EMAIL="WizDesk <noreply@example.com>",
            WEB_CONCURRENCY="1",
            CORS_ALLOW_ALL_ORIGINS="False",
        )
        result = subprocess.run(
            [sys.executable, "manage.py", "check_production_config"],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        missing_key = env.copy()
        missing_key.pop("RESEND_API_KEY")
        invalid_email = subprocess.run(
            [sys.executable, "manage.py", "check_production_config"],
            env=missing_key, capture_output=True, text=True,
        )
        self.assertNotEqual(invalid_email.returncode, 0)
        self.assertIn("RESEND_API_KEY", invalid_email.stderr)
        strict = env.copy()
        strict["SECURE_HSTS_INCLUDE_SUBDOMAINS"] = "True"
        strict["SECURE_HSTS_PRELOAD"] = "True"
        django_check = subprocess.run(
            [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
            env=strict, capture_output=True, text=True,
        )
        self.assertEqual(django_check.returncode, 0, django_check.stderr)
        parsed = subprocess.run(
            [sys.executable, "-c", "from wizdesk_backend import settings; "
             "print(settings.DATABASES['default']['CONN_MAX_AGE']); "
             "print(settings.DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'])"],
            env=env, capture_output=True, text=True, check=True,
        )
        self.assertEqual(parsed.stdout.splitlines(), ["0", "True"])
        env["SECURE_SSL_REDIRECT"] = "False"
        invalid = subprocess.run(
            [sys.executable, "manage.py", "check_production_config"],
            env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("SECURE_SSL_REDIRECT", invalid.stderr)
        env["SECURE_SSL_REDIRECT"] = "True"
        env["FRONTEND_URL"] = "https://unexpected.example.com"
        invalid_origin = subprocess.run(
            [sys.executable, "manage.py", "check_production_config"],
            env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(invalid_origin.returncode, 0)
        self.assertIn("FRONTEND_URL", invalid_origin.stderr)
