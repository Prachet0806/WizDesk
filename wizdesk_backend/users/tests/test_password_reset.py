import re
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.core import mail
from django.core.cache import cache
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import AuditEvent, Team, User


class PasswordResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.team = Team.objects.create(code="RESET1", name="Reset")
        self.user = User.objects.create_user(
            username="reset@example.com",
            email="reset@example.com",
            password="OldPassword!2031",
            name="Reset User",
            role=User.Role.LEADER,
            status=User.Status.APPROVED,
            team=self.team,
            email_verified=True,
        )
        self.team.leader = self.user
        self.team.save(update_fields=["leader"])

    def reset_link(self):
        request = APIClient().post(
            "/api/auth/password-reset/request/",
            {"email": self.user.email},
            format="json",
        )
        self.assertEqual(request.status_code, 202)
        self.assertEqual(len(mail.outbox), 1)
        url = re.search(r"https?://\S+", mail.outbox[0].body).group(0)
        self.assertEqual(urlparse(url).path, "/reset-password.html")
        query = parse_qs(urlparse(url).fragment)
        return {"uid": query["uid"][0], "token": query["token"][0]}

    def csrf_headers(self, client):
        response = client.get("/api/auth/csrf/")
        return {"HTTP_X_CSRFTOKEN": response.data["csrfToken"]}

    def test_request_is_generic_and_reset_revokes_old_access_and_refresh(self):
        old_refresh = RefreshToken.for_user(self.user)
        old_access = str(old_refresh.access_token)
        link = self.reset_link()
        unknown = APIClient().post(
            "/api/auth/password-reset/request/",
            {"email": "unknown@example.com"},
            format="json",
        )
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(len(mail.outbox), 1)
        weak = APIClient().post(
            "/api/auth/password-reset/confirm/",
            {**link, "password": "short"},
            format="json",
        )
        self.assertEqual(weak.status_code, 400)
        success = APIClient().post(
            "/api/auth/password-reset/confirm/",
            {**link, "password": "NewPassword!2031"},
            format="json",
        )
        self.assertEqual(success.status_code, 200, success.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword!2031"))
        self.assertTrue(
            AuditEvent.objects.filter(
                action="account.password_reset", target_id=str(self.user.pk)
            ).exists()
        )
        self.assertEqual(
            APIClient().post(
                "/api/auth/password-reset/confirm/",
                {**link, "password": "AgainPassword!2031"},
                format="json",
            ).status_code,
            400,
        )
        authenticated = APIClient()
        authenticated.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        self.assertEqual(authenticated.get("/api/auth/me/").status_code, 401)
        refresh_client = APIClient()
        csrf = self.csrf_headers(refresh_client)
        refresh_client.cookies["wizdesk_refresh"] = str(old_refresh)
        self.assertEqual(
            refresh_client.post(
                "/api/token/refresh/", {}, format="json", **csrf
            ).status_code,
            401,
        )
        login_client = APIClient()
        csrf = self.csrf_headers(login_client)
        self.assertEqual(
            login_client.post(
                "/api/auth/login/",
                {"email": self.user.email, "password": "NewPassword!2031"},
                format="json",
                **csrf,
            ).status_code,
            200,
        )

    def test_expired_and_malformed_links_are_rejected(self):
        with patch.object(default_token_generator, "_now", return_value=datetime(2030, 1, 1)):
            link = self.reset_link()
        with patch.object(
            default_token_generator,
            "_now",
            return_value=datetime(2030, 1, 1) + timedelta(hours=2),
        ):
            expired = APIClient().post(
                "/api/auth/password-reset/confirm/",
                {**link, "password": "NewPassword!2031"},
                format="json",
            )
        self.assertEqual(expired.status_code, 400)
        self.assertEqual(
            APIClient().post(
                "/api/auth/password-reset/confirm/",
                {"uid": "invalid", "token": "invalid", "password": "NewPassword!2031"},
                format="json",
            ).status_code,
            400,
        )

    def test_delivery_failure_keeps_generic_response(self):
        with patch("users.views.send_mail", side_effect=OSError("SMTP offline")):
            response = APIClient().post(
                "/api/auth/password-reset/request/",
                {"email": self.user.email},
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("token", str(response.data))

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_production_console_backend_does_not_log_reset_link(self):
        with patch("users.views.send_mail") as send:
            response = APIClient().post(
                "/api/auth/password-reset/request/",
                {"email": self.user.email},
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        send.assert_not_called()
