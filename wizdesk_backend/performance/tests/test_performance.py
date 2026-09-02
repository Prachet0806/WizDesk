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


class PerformanceTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.team = Team.objects.create(code="PF001", name="Perf Team")
        self.leader = User.objects.create_user(username="lpf@test.com", email="lpf@test.com", password="p",
                                                name="Perf Leader", role=User.Role.LEADER, status=User.Status.APPROVED, team=self.team)
        self.member = User.objects.create_user(username="mpf@test.com", email="mpf@test.com", password="p",
                                                name="Perf Member", role=User.Role.MEMBER, status=User.Status.APPROVED, team=self.team)
        self.team.leader = self.leader; self.team.save()

        self.lc = APIClient(); auth(self.lc, self.leader)

    def test_performance_response_shape(self):
        r = self.lc.get(f'/api/performance/team/{self.team.code}/')
        self.assertEqual(r.status_code, 200)
        required = {'totalTasks', 'completedTasks', 'activeTasks', 'productivityScore', 'totalMembers', 'memberStats'}
        self.assertTrue(required.issubset(r.data.keys()))
        self.assertIsInstance(r.data['memberStats'], list)