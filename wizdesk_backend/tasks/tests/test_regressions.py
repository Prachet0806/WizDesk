from io import StringIO
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.db import IntegrityError, transaction
from django.test.utils import CaptureQueriesContext
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User, Team, TeamTransferRequest
from users.views import verification_token
from tasks.models import Task, Subtask


class RegressionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.team = Team.objects.create(code='REG001', name='Regression')
        self.leader = self.user('leader', User.Role.LEADER)
        self.member = self.user('member')
        self.team.leader = self.leader
        self.team.save()
        self.client = self.client_for(self.leader)

    def user(self, name, role=User.Role.MEMBER):
        return User.objects.create_user(username=name, email=f'{name}@example.com',
            password='BlueRiver!2031', name=name, role=role, status=User.Status.APPROVED,
            team=self.team, email_verified=True)

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        return client

    def task(self, children=None):
        response = self.client.post('/api/tasks/', {'title': 'Original', 'subtasks': children or []}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_invalid_second_deadline_leaves_no_partial_task(self):
        response = self.client.post('/api/tasks/', {'title': 'Invalid', 'subtasks': [
            {'title': 'Valid'}, {'title': 'Bad date', 'deadline': 'invalid'}]}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.exists())
        self.assertFalse(Subtask.objects.exists())

    def test_naive_deadline_rejected_and_offset_normalized(self):
        payload = {'title': 'Time', 'subtasks': [{'title': 'S', 'deadline': '2030-02-01T10:00'}]}
        self.assertEqual(self.client.post('/api/tasks/', payload, format='json').status_code, 400)
        payload['subtasks'][0]['deadline'] = '2030-02-01T10:00:00+05:30'
        response = self.client.post('/api/tasks/', payload, format='json')
        self.assertEqual(response.data['subtasks'][0]['deadline'], '2030-02-01T04:30:00Z')

    def test_member_cannot_create_and_invalid_status_rejected(self):
        response = self.client_for(self.member).post('/api/tasks/', {'title': 'Forbidden'}, format='json')
        self.assertEqual(response.status_code, 403)
        response = self.client.post('/api/tasks/', {'title': 'Invalid', 'status': 'bogus'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.exists())

    def test_database_rejects_invalid_states_and_case_duplicate_email(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Task.objects.create(title='Invalid', team=self.team, status='bogus')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username='duplicate', email='LEADER@EXAMPLE.COM', password='BlueRiver!2031')

    def test_aggregate_edit_adds_updates_and_deletes(self):
        original = self.task([{'title': 'Keep'}, {'title': 'Remove'}])
        response = self.client.put(f"/api/tasks/{original['id']}/", {
            'title': 'Edited', 'expected_updated_at': original['updated_at'],
            'subtasks': [{'id': original['subtasks'][0]['id'], 'title': 'Changed'}, {'title': 'New'}],
            'deleted_subtask_ids': [original['subtasks'][1]['id']]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(Subtask.objects.values_list('title', flat=True)), {'Changed', 'New'})
        self.assertEqual(response.data['task']['title'], 'Edited')

    def test_semantic_failure_rolls_back_entire_edit(self):
        original = self.task([{'title': 'Keep'}])
        response = self.client.put(f"/api/tasks/{original['id']}/", {
            'title': 'Must roll back', 'status': 'completed',
            'subtasks': [{'id': original['subtasks'][0]['id'], 'title': 'Must also roll back'}]}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Task.objects.get().title, 'Original')
        self.assertEqual(Subtask.objects.get().title, 'Keep')

    def test_stale_revision_and_foreign_child_ids_rejected(self):
        first = self.task([{'title': 'First'}])
        second = self.task([{'title': 'Second'}])
        url = f"/api/tasks/{first['id']}/"
        response = self.client.put(url, {'subtasks': [{'id': second['subtasks'][0]['id'], 'title': 'Foreign'}]}, format='json')
        self.assertEqual(response.status_code, 400)
        self.client.put(url, {'title': 'Changed'}, format='json')
        response = self.client.put(url, {'title': 'Stale', 'expected_updated_at': first['updated_at']}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Task.objects.get(pk=first['id']).title, 'Changed')

    def test_unknown_priority_preserves_existing_child_priority(self):
        original = self.task([{'title': 'S', 'priority': 'high'}])
        response = self.client.put(f"/api/tasks/{original['id']}/", {
            'priority': 'low', 'subtasks': [{'id': original['subtasks'][0]['id'], 'priority': 'unknown'}]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Subtask.objects.get().priority, 'high')

    def test_deleting_incomplete_child_completes_parent(self):
        original = self.task([{'title': 'Done', 'assigned_to': str(self.member.pk)}, {'title': 'Delete'}])
        self.client.post(f"/api/tasks/subtask/{original['subtasks'][0]['id']}/progress/", {'progress': 'completed'}, format='json')
        self.client.delete(f"/api/tasks/subtask/{original['subtasks'][1]['id']}/")
        self.assertEqual(Task.objects.get().status, Task.Status.COMPLETED)

    def test_archived_parent_stays_archived_on_aggregate_edit(self):
        original = self.task([{'title': 'S'}])
        self.client.put(f"/api/tasks/{original['id']}/", {'status': 'archived', 'subtasks': [{'title': 'New'}]}, format='json')
        self.assertEqual(Task.objects.get().status, Task.Status.ARCHIVED)

    def test_removal_preserves_completed_history_and_releases_open_work(self):
        original = self.task([{'title': 'Done', 'assigned_to': str(self.member.pk)}, {'title': 'Open', 'assigned_to': str(self.member.pk)}])
        self.client.post(f"/api/tasks/subtask/{original['subtasks'][0]['id']}/progress/", {'progress': 'completed'}, format='json')
        member_client = self.client_for(self.member)
        target = Team.objects.create(code='TARGET', name='Target', leader=self.leader)
        transfer = TeamTransferRequest.objects.create(member=self.member, current_team=self.team, future_team=target)
        response = self.client.delete(f'/api/auth/team/{self.team.code}/member/{self.member.pk}/')
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db(); transfer.refresh_from_db()
        self.assertIsNone(self.member.team_id)
        self.assertEqual(transfer.status, TeamTransferRequest.Status.REJECTED)
        self.assertEqual(Subtask.objects.get(title='Done').assigned_to_id, self.member.pk)
        self.assertIsNone(Subtask.objects.get(title='Open').assigned_to_id)
        self.assertEqual(member_client.get('/api/auth/me/').status_code, 401)

    def test_pending_and_rejected_tokens_cannot_refresh(self):
        refresh = str(RefreshToken.for_user(self.member))
        for state in (User.Status.PENDING, User.Status.REJECTED):
            self.member.status = state; self.member.save()
            response = APIClient().post('/api/token/refresh/', {'refresh': refresh}, format='json')
            self.assertEqual(response.status_code, 401)

    def test_rotation_and_logout_blacklist(self):
        anonymous = APIClient()
        original = str(RefreshToken.for_user(self.member))
        first = anonymous.post('/api/token/refresh/', {'refresh': original}, format='json')
        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(first.data['refresh'], original)
        self.assertEqual(anonymous.post('/api/token/refresh/', {'refresh': original}, format='json').status_code, 401)
        second = anonymous.post('/api/token/refresh/', {'refresh': first.data['refresh']}, format='json')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(anonymous.post('/api/auth/logout/', {'refresh': second.data['refresh']}, format='json').status_code, 204)
        self.assertEqual(anonymous.post('/api/token/refresh/', {'refresh': second.data['refresh']}, format='json').status_code, 401)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_unverified_login_access_and_refresh_blocked(self):
        self.member.email_verified = False; self.member.save()
        anonymous = APIClient()
        self.assertEqual(anonymous.post('/api/auth/login/', {'email': self.member.email, 'password': 'BlueRiver!2031'}, format='json').status_code, 403)
        self.assertEqual(self.client_for(self.member).get('/api/auth/me/').status_code, 401)
        self.assertEqual(anonymous.post('/api/token/refresh/', {'refresh': str(RefreshToken.for_user(self.member))}, format='json').status_code, 401)
        self.assertEqual(self.client.post('/api/tasks/', {'title': 'Assignment', 'subtasks': [
            {'title': 'S', 'assigned_to': str(self.member.pk)}]}, format='json').status_code, 400)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_email_token_purpose_expiry_and_idempotent_verification(self):
        self.leader.team = None; self.leader.email_verified = False; self.leader.save()
        token = verification_token(self.leader)
        payload = {'token': token, 'uid': urlsafe_base64_encode(force_bytes(self.leader.pk))}
        anonymous = APIClient()
        self.assertEqual(anonymous.post('/api/auth/verify-member-email/', payload, format='json').status_code, 400)
        with patch('django.core.signing.time.time', return_value=1):
            expired = verification_token(self.leader)
        self.assertEqual(anonymous.post('/api/auth/verify-email/', {**payload, 'token': expired}, format='json').status_code, 400)
        first = anonymous.post('/api/auth/verify-email/', payload, format='json')
        second = anonymous.post('/api/auth/verify-email/', payload, format='json')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['teamCode'], second.data['teamCode'])
        self.assertEqual(Team.objects.filter(leader=self.leader).count(), 2)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_smtp_failure_is_recoverable_without_claiming_delivery(self):
        payload = {'name': 'Zoë O’Neil'.replace('’', "'"), 'email': 'new@example.com', 'password': 'OceanWaves!2031', 'teamName': 'New'}
        with patch('users.views.send_mail', side_effect=OSError('SMTP unavailable')):
            with self.captureOnCommitCallbacks(execute=True):
                response = APIClient().post('/api/auth/send-verification/', payload, format='json')
        self.assertEqual(response.status_code, 202)
        self.assertIsNone(response.data['emailSent'])
        self.assertNotIn('verificationToken', response.data)
        self.assertTrue(User.objects.filter(email='new@example.com', email_verified=False).exists())
        with patch('users.views.send_mail', return_value=1) as send:
            resent = APIClient().post('/api/auth/resend-verification/', {'email': 'new@example.com'}, format='json')
        self.assertEqual(resent.status_code, 202)
        self.assertEqual(send.call_count, 1)

    def test_health_bypasses_throttles_and_readiness_reports_database_failure(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_AUTHORIZATION='Bearer invalid')
        for _ in range(105):
            self.assertEqual(anonymous.get('/health/').status_code, 200)
        with patch('users.views.connection.cursor', side_effect=OSError('offline')):
            self.assertEqual(anonymous.get('/ready/').status_code, 503)

    def test_unknown_urls_return_real_404_and_array_body_returns_400(self):
        self.assertEqual(APIClient().get('/missing-page.html').status_code, 404)
        self.assertEqual(APIClient().get('/api/missing/').status_code, 404)
        for path in ('/api/auth/login/', '/api/auth/send-verification/', '/api/auth/logout/'):
            self.assertEqual(APIClient().post(path, [], format='json').status_code, 400)

    def test_pagination_and_assigned_queries_are_bounded(self):
        task = Task.objects.create(title='Same', team=self.team, created_by=self.leader)
        Subtask.objects.bulk_create([Subtask(task=task, title=f'S{i}', assigned_to=self.member) for i in range(25)])
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(f'/api/tasks/user/{self.member.pk}/subtasks/')
        self.assertEqual(response.data['count'], 25)
        self.assertEqual(len(response.data['results']), 20)
        self.assertIsNotNone(response.data['next'])
        self.assertLessEqual(len(captured), 6)
        self.assertEqual(response.data['results'][0]['task_id'], str(task.pk))

    def test_current_team_performance_excludes_old_team_history(self):
        old = Team.objects.create(code='OLD001', name='Old')
        task = Task.objects.create(title='Historical', team=old, created_by=self.leader)
        Subtask.objects.create(task=task, title='Done', assigned_to=self.member, progress='completed', status='completed')
        response = self.client.get(f'/api/performance/team/{self.team.code}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['memberStats'][0]['assigned_tasks'], 0)

    def test_repair_dry_run_does_not_mutate_and_apply_repairs_derived_state(self):
        task = Task.objects.create(title='State', team=self.team, created_by=self.leader)
        Subtask.objects.create(task=task, title='S', assigned_to=self.member, progress='assigned', status='available')
        output = StringIO()
        call_command('repair_task_states', stdout=output)
        self.assertEqual(Subtask.objects.get().status, 'available')
        call_command('repair_task_states', apply=True, stdout=output)
        self.assertEqual(Subtask.objects.get().status, 'assigned')

    def test_repair_releases_rejected_members_unfinished_assignments(self):
        task = Task.objects.create(title='Rejected assignment', team=self.team, created_by=self.leader)
        child = Subtask.objects.create(task=task, title='Open', assigned_to=self.member, progress='in_progress', status='taken')
        self.member.status = 'REJECTED'; self.member.save()
        call_command('repair_task_states', apply=True, stdout=StringIO())
        child.refresh_from_db()
        self.assertIsNone(child.assigned_to_id)
        self.assertEqual(child.status, 'available')
