from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.test import TransactionTestCase
from django.db import connection, connections
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User, Team, TeamTransferRequest
from tasks.models import Task, Subtask


@skipUnless(connection.vendor == 'postgresql', 'Row-lock races require PostgreSQL')
class ConcurrentMutationTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.team = Team.objects.create(code='RACE01', name='Race')
        self.leader = self.user('race-leader', User.Role.LEADER)
        self.first = self.user('race-first')
        self.second = self.user('race-second')
        self.team.leader = self.leader; self.team.save()
        self.task = Task.objects.create(title='Race', team=self.team, created_by=self.leader)

    def user(self, name, role=User.Role.MEMBER):
        return User.objects.create_user(username=name, email=f'{name}@example.com', password='BlueRiver!2031',
            name=name, role=role, status=User.Status.APPROVED, team=self.team, email_verified=True)

    def parallel(self, operations):
        barrier = Barrier(len(operations))
        tokens = [str(RefreshToken.for_user(user).access_token) for user, _, _, _ in operations]
        def execute(index):
            user, method, url, payload = operations[index]
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens[index]}')
            try:
                barrier.wait(timeout=10)
                response = getattr(client, method)(url, payload, format='json')
                return response.status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(execute, index) for index in range(len(operations))]
            return [future.result(timeout=20) for future in futures]

    def test_two_claims_have_one_winner(self):
        child = Subtask.objects.create(task=self.task, title='Claim')
        url = f'/api/tasks/subtask/{child.pk}/take/'
        outcomes = self.parallel([(self.first, 'post', url, {}), (self.second, 'post', url, {})])
        self.assertEqual(sorted(outcomes), [200, 409])
        child.refresh_from_db()
        self.assertIn(child.assigned_to_id, [self.first.pk, self.second.pk])

    def test_two_rotations_of_one_refresh_have_one_winner(self):
        refresh = str(RefreshToken.for_user(self.first))
        outcomes = self.parallel([(self.first, 'post', '/api/token/refresh/', {'refresh': refresh}),
            (self.first, 'post', '/api/token/refresh/', {'refresh': refresh})])
        self.assertEqual(sorted(outcomes), [200, 401])

    def test_last_two_completions_recompute_parent_under_lock(self):
        first = Subtask.objects.create(task=self.task, title='First', assigned_to=self.first, progress='assigned', status='assigned')
        second = Subtask.objects.create(task=self.task, title='Second', assigned_to=self.second, progress='assigned', status='assigned')
        outcomes = self.parallel([(self.first, 'post', f'/api/tasks/subtask/{first.pk}/progress/', {'progress': 'completed'}),
            (self.second, 'post', f'/api/tasks/subtask/{second.pk}/progress/', {'progress': 'completed'})])
        self.assertEqual(outcomes, [200, 200])
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'completed')

    def test_assignment_racing_transfer_cannot_leave_old_team_work_assigned(self):
        future = Team.objects.create(code='RACE02', name='Future')
        future_leader = self.user('future-leader', User.Role.LEADER)
        future_leader.team = future; future_leader.save()
        future.leader = future_leader; future.save()
        transfer = TeamTransferRequest.objects.create(member=self.first, current_team=self.team,
            future_team=future, status='PENDING_FUTURE')
        child = Subtask.objects.create(task=self.task, title='Assignment')
        outcomes = self.parallel([(self.leader, 'put', f'/api/tasks/subtask/{child.pk}/', {'assigned_to': str(self.first.pk)}),
            (future_leader, 'post', f'/api/auth/transfer/{transfer.pk}/process/', {'action': 'approve'})])
        self.assertIn(outcomes[0], [200, 400])
        self.assertEqual(outcomes[1], 200)
        self.first.refresh_from_db(); child.refresh_from_db()
        self.assertEqual(self.first.team_id, future.pk)
        self.assertIsNone(child.assigned_to_id)
