from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import Team

User = get_user_model()


def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")


class PermissionTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.team = Team.objects.create(code="PM001", name="Perm Team")
        self.leader = User.objects.create_user(username="lp@test.com", email="lp@test.com", password="p",
                                                name="Perm Leader", role=User.Role.LEADER, status=User.Status.APPROVED, team=self.team)
        self.member = User.objects.create_user(username="mp@test.com", email="mp@test.com", password="p",
                                                name="Perm Member", role=User.Role.MEMBER, status=User.Status.APPROVED, team=self.team)
        self.team.leader = self.leader; self.team.save()

        self.lc = APIClient(); auth(self.lc, self.leader)
        self.mc = APIClient(); auth(self.mc, self.member)

    def test_member_cannot_delete_task(self):
        r = self.lc.post('/api/tasks/', {'title': 'T'}, format='json')
        task_id = r.data['id']
        r = self.mc.delete(f'/api/tasks/{task_id}/')
        self.assertEqual(r.status_code, 403)

    def test_member_cannot_delete_subtask(self):
        r = self.lc.post('/api/tasks/', {'title': 'T', 'subtasks': [{'title': 'S'}]}, format='json')
        sub_id = r.data['subtasks'][0]['id']
        r = self.mc.delete(f'/api/tasks/subtask/{sub_id}/')
        self.assertEqual(r.status_code, 403)

    def test_member_cannot_update_subtask_assignee(self):
        r = self.lc.post('/api/tasks/', {'title': 'T', 'subtasks': [{'title': 'S'}]}, format='json')
        sub_id = r.data['subtasks'][0]['id']
        r = self.mc.put(f'/api/tasks/subtask/{sub_id}/', {'assigned_to': str(self.leader.id)}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_member_cannot_access_performance(self):
        r = self.mc.get(f'/api/performance/team/{self.team.code}/')
        self.assertEqual(r.status_code, 403)
