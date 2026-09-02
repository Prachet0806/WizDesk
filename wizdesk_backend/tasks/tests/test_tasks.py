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
from tasks.models import Task, Subtask

User = get_user_model()


def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")


class TaskCRUDTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.team = Team.objects.create(code="TC001", name="Task Team")
        self.leader = User.objects.create_user(username="lt@test.com", email="lt@test.com", password="p",
                                                name="Task Leader", role=User.Role.LEADER, status=User.Status.APPROVED, team=self.team)
        self.member = User.objects.create_user(username="mt@test.com", email="mt@test.com", password="p",
                                                name="Task Member", role=User.Role.MEMBER, status=User.Status.APPROVED, team=self.team)
        self.team.leader = self.leader; self.team.save()

        self.lc = APIClient(); auth(self.lc, self.leader)
        self.mc = APIClient(); auth(self.mc, self.member)

    def test_create_task_with_priority(self):
        r = self.lc.post('/api/tasks/', {'title': 'Pri Task', 'priority': 'high', 'subtasks': [
            {'title': 'Sub 1', 'priority': 'low', 'assigned_to': str(self.member.id)},
        ]}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['priority'], 'high')
        self.assertEqual(r.data['subtasks'][0]['priority'], 'low')

    def test_create_task_invalid_priority_falls_back(self):
        r = self.lc.post('/api/tasks/', {'title': 'Bad Pri', 'priority': 'urgent'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['priority'], 'medium')

    def test_create_task_cross_team_assignee_rejected(self):
        other_team = Team.objects.create(code="OT002", name="Other")
        other_member = User.objects.create_user(username="om@test.com", email="om@test.com", password="p",
                                                 name="Other Member", role=User.Role.MEMBER, status=User.Status.APPROVED, team=other_team)
        r = self.lc.post('/api/tasks/', {'title': 'Cross', 'subtasks': [{'title': 'S', 'assigned_to': str(other_member.id)}]}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.data['subtasks'][0]['assigned_to'])

    def test_task_detail_put_member_blocked(self):
        r = self.lc.post('/api/tasks/', {'title': 'T1'}, format='json')
        task_id = r.data['id']
        r = self.mc.put(f'/api/tasks/{task_id}/', {'title': 'Hax'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_task_detail_put_leader_updates_priority(self):
        r = self.lc.post('/api/tasks/', {'title': 'T1'}, format='json')
        task_id = r.data['id']
        r = self.lc.put(f'/api/tasks/{task_id}/', {'priority': 'low'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['task']['priority'], 'low')


class SubtaskStateSyncTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.team = Team.objects.create(code="SS001", name="Sync Team")
        self.leader = User.objects.create_user(username="ls@test.com", email="ls@test.com", password="p",
                                                name="Sync Leader", role=User.Role.LEADER, status=User.Status.APPROVED, team=self.team)
        self.member = User.objects.create_user(username="ms@test.com", email="ms@test.com", password="p",
                                                name="Sync Member", role=User.Role.MEMBER, status=User.Status.APPROVED, team=self.team)
        self.team.leader = self.leader; self.team.save()

        self.lc = APIClient(); auth(self.lc, self.leader)
        self.mc = APIClient(); auth(self.mc, self.member)

    def test_take_subtask_sets_taken_and_calls_sync(self):
        r = self.lc.post('/api/tasks/', {'title': 'T', 'subtasks': [{'title': 'S'}]}, format='json')
        sub_id = r.data['subtasks'][0]['id']
        r = self.mc.post(f'/api/tasks/subtask/{sub_id}/take/')
        self.assertEqual(r.status_code, 200)
        sub = Subtask.objects.get(pk=sub_id)
        self.assertEqual(sub.status, 'taken')
        self.assertEqual(sub.progress, 'in_progress')

    def test_update_progress_validates_value(self):
        r = self.lc.post('/api/tasks/', {'title': 'T', 'subtasks': [{'title': 'S', 'assigned_to': str(self.member.id)}]}, format='json')
        sub_id = r.data['subtasks'][0]['id']
        r = self.mc.post(f'/api/tasks/subtask/{sub_id}/progress/', {'progress': 'bogus'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.mc.post(f'/api/tasks/subtask/{sub_id}/progress/', {'progress': 'testing'}, format='json')
        self.assertEqual(r.status_code, 200)
        sub = Subtask.objects.get(pk=sub_id)
        self.assertEqual(sub.progress, 'testing')

    def test_all_subtasks_complete_marks_task_completed(self):
        r = self.lc.post('/api/tasks/', {'title': 'T', 'subtasks': [{'title': 'S1'}, {'title': 'S2'}]}, format='json')
        task_id = r.data['id']
        sub1 = Subtask.objects.get(pk=r.data['subtasks'][0]['id'])
        sub2 = Subtask.objects.get(pk=r.data['subtasks'][1]['id'])
        sub1.progress = 'completed'; sub1.sync_state()
        sub2.progress = 'completed'; sub2.sync_state()
        task = Task.objects.get(pk=task_id)
        self.assertEqual(task.status, 'completed')