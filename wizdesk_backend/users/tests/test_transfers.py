from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import Team, TeamTransferRequest
from tasks.models import Task, Subtask

User = get_user_model()


def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")


class TransferFlowTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.team_a = Team.objects.create(code="TA001", name="Team A")
        self.team_b = Team.objects.create(code="TB001", name="Team B")
        self.leader_a = User.objects.create_user(username="la@test.com", email="la@test.com", password="p",
                                                  name="Leader A", role=User.Role.LEADER, status=User.Status.APPROVED, team=self.team_a)
        self.leader_b = User.objects.create_user(username="lb@test.com", email="lb@test.com", password="p",
                                                  name="Leader B", role=User.Role.LEADER, status=User.Status.APPROVED, team=self.team_b)
        self.member = User.objects.create_user(username="m@test.com", email="m@test.com", password="p",
                                                name="Member", role=User.Role.MEMBER, status=User.Status.APPROVED, team=self.team_a)
        self.team_a.leader = self.leader_a; self.team_a.save()
        self.team_b.leader = self.leader_b; self.team_b.save()

        self.la_c = APIClient(); auth(self.la_c, self.leader_a)
        self.lb_c = APIClient(); auth(self.lb_c, self.leader_b)
        self.m_c = APIClient(); auth(self.m_c, self.member)

    def test_same_team_transfer_rejected(self):
        r = self.m_c.post('/api/auth/transfer/request/', {'future_team_code': self.team_a.code}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_leader_cannot_request_transfer(self):
        r = self.la_c.post('/api/auth/transfer/request/', {'future_team_code': self.team_b.code}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_full_approval_moves_member_and_unassigns_subtasks(self):
        r = self.la_c.post('/api/tasks/', {'title': 'T', 'subtasks': [{'title': 'S', 'assigned_to': str(self.member.id)}]}, format='json')
        sub_id = r.data['subtasks'][0]['id']

        r = self.m_c.post('/api/auth/transfer/request/', {'future_team_code': self.team_b.code}, format='json')
        self.assertEqual(r.status_code, 201)
        req_id = r.data['id']

        r = self.la_c.post(f'/api/auth/transfer/{req_id}/process/', {'action': 'approve'}, format='json')
        self.assertEqual(r.status_code, 200)

        r = self.lb_c.post(f'/api/auth/transfer/{req_id}/process/', {'action': 'approve'}, format='json')
        self.assertEqual(r.status_code, 200)

        self.member.refresh_from_db()
        self.assertEqual(self.member.team, self.team_b)

        sub = Subtask.objects.get(pk=sub_id)
        self.assertIsNone(sub.assigned_to)
        self.assertEqual(sub.status, 'available')

    def test_reject_sets_rejected_status(self):
        r = self.m_c.post('/api/auth/transfer/request/', {'future_team_code': self.team_b.code}, format='json')
        req_id = r.data['id']
        r = self.la_c.post(f'/api/auth/transfer/{req_id}/process/', {'action': 'reject'}, format='json')
        self.assertEqual(r.status_code, 200)
        req = TeamTransferRequest.objects.get(pk=req_id)
        self.assertEqual(req.status, 'REJECTED')
