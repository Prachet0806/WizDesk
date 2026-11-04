from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import AuditEvent, Team, User


def authorized(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


class TeamCodeRotationTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(code="JOIN01", name="Team")
        self.leader = User.objects.create_user(
            username="leader@example.com", email="leader@example.com", password="Pass!2031",
            name="Leader", role=User.Role.LEADER, status=User.Status.APPROVED,
            team=self.team, email_verified=True,
        )
        self.team.leader = self.leader
        self.team.save(update_fields=["leader"])
        self.member = User.objects.create_user(
            username="member@example.com", email="member@example.com", password="Pass!2031",
            name="Member", role=User.Role.MEMBER, status=User.Status.APPROVED,
            team=self.team, email_verified=True,
        )

    def test_leader_can_rotate_code_and_old_code_stops_accepting_registrations(self):
        response = authorized(self.leader).post("/api/auth/team/JOIN01/rotate-code/")
        self.assertEqual(response.status_code, 200, response.data)
        new_code = response.data["team_code"]
        self.assertNotEqual(new_code, "JOIN01")
        self.team.refresh_from_db()
        self.assertEqual(self.team.code, new_code)
        self.assertEqual(
            AuditEvent.objects.filter(action="team.code_rotated", team=self.team).count(), 1
        )
        old = APIClient().post(
            "/api/auth/send-member-verification/",
            {"email": "new1@example.com", "password": "OceanWaves!2031", "name": "New Member", "team_code": "JOIN01"},
            format="json",
        )
        self.assertEqual(old.status_code, 400)
        current = APIClient().post(
            "/api/auth/send-member-verification/",
            {"email": "new2@example.com", "password": "OceanWaves!2031", "name": "New Member", "team_code": new_code},
            format="json",
        )
        self.assertEqual(current.status_code, 201)

    def test_member_and_stale_code_cannot_rotate(self):
        path = "/api/auth/team/JOIN01/rotate-code/"
        self.assertEqual(authorized(self.member).post(path).status_code, 403)
        self.assertEqual(authorized(self.leader).post("/api/auth/team/WRONG/rotate-code/").status_code, 403)
        self.team.refresh_from_db()
        self.assertEqual(self.team.code, "JOIN01")

    def test_deleting_leader_does_not_delete_team(self):
        with self.assertRaises(ProtectedError):
            self.leader.delete()
        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_failed_verification_delivery_can_be_retried(self):
        from urllib.parse import parse_qs, urlparse
        import re
        from unittest.mock import patch
        from django.core import mail
        user = User.objects.create_user(
            username="retry@example.com", email="retry@example.com", password="Pass!2031",
            name="Retry", role=User.Role.MEMBER, status=User.Status.PENDING,
            team=self.team, email_verified=False,
        )
        with patch("users.views.send_mail", side_effect=OSError("SMTP offline")):
            failed = APIClient().post("/api/auth/resend-verification/", {"email": user.email}, format="json")
        self.assertEqual(failed.status_code, 202)
        self.assertFalse(user.email_verified)
        retried = APIClient().post("/api/auth/resend-verification/", {"email": user.email}, format="json")
        self.assertEqual(retried.status_code, 202)
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https?://\S+", mail.outbox[0].body).group(0)
        query = parse_qs(urlparse(link).query)
        verified = APIClient().post(
            "/api/auth/verify-member-email/",
            {"uid": query["uid"][0], "token": query["token"][0]},
            format="json",
        )
        self.assertEqual(verified.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
