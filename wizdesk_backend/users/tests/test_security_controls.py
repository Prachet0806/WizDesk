from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

from users.models import Team, User
from users.views import _send_verification_email


class SecurityControlTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(code="SECU01", name="Security")
        self.user = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="BlueRiver!2031",
            name="Admin",
            team=self.team,
            role=User.Role.LEADER,
            status=User.Status.APPROVED,
            email_verified=True,
        )
        self.team.leader = self.user
        self.team.save(update_fields=["leader"])

    def test_admin_session_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post("/admin/").status_code, 403)

    def test_session_cookie_does_not_authenticate_bearer_api(self):
        client = APIClient()
        client.force_login(self.user)
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)

    @override_settings(
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=True,
    )
    def test_https_response_declares_hsts_policy(self):
        response = APIClient().get("/health/", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Strict-Transport-Security"],
            "max-age=31536000; includeSubDomains; preload",
        )

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_production_console_backend_never_prints_verification_link(self):
        with patch("users.views.send_mail") as send:
            self.assertFalse(_send_verification_email(self.user))
        send.assert_not_called()
