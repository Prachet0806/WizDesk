import os
os.environ['ALLOWED_HOSTS'] = 'testserver,localhost,127.0.0.1'

import sys
sys.path.insert(0, r"C:\Users\prach\Documents\WIZDESK\wizdesk_backend")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wizdesk_backend.settings')

import django
django.setup()

from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import Team

User = get_user_model()


def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")


class AuthFlowTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.team = Team.objects.create(code="TF001", name="Test Team")
        self.leader = User.objects.create_user(
            username="leader@test.com", email="leader@test.com", password="p",
            name="Test Leader", role=User.Role.LEADER, status=User.Status.APPROVED, team=self.team
        )
        self.member = User.objects.create_user(
            username="member@test.com", email="member@test.com", password="p",
            name="Test Member", role=User.Role.MEMBER, status=User.Status.APPROVED, team=self.team
        )
        self.team.leader = self.leader
        self.team.save()

        self.lc = APIClient()
        self.mc = APIClient()
        auth(self.lc, self.leader)
        auth(self.mc, self.member)

    def test_login_returns_token_and_user(self):
        client = APIClient()
        r = client.post('/api/auth/login/', {'email': 'leader@test.com', 'password': 'p'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('token', r.data)
        self.assertIn('user', r.data)
        self.assertEqual(r.data['user']['role'], 'LEADER')

    def test_member_cannot_create_task_without_team(self):
        noteam = User.objects.create_user(username="nt@test.com", email="nt@test.com", password="p",
                                           name="NoTeam", role=User.Role.MEMBER, status=User.Status.APPROVED)
        nc = APIClient()
        auth(nc, noteam)
        r = nc.post('/api/tasks/', {'title': 'NoTeam Task'}, format='json')
        self.assertIn(r.status_code, (400, 403))

    def test_member_cannot_access_other_team_tasks(self):
        other_team = Team.objects.create(code="OT001", name="Other")
        other_leader = User.objects.create_user(username="ol@test.com", email="ol@test.com", password="p",
                                                name="Other Leader", role=User.Role.LEADER, status=User.Status.APPROVED, team=other_team)
        other_team.leader = other_leader; other_team.save()
        oc = APIClient(); auth(oc, other_leader)
        r = oc.get(f'/api/tasks/team/{self.team.code}/')
        self.assertEqual(r.status_code, 403)