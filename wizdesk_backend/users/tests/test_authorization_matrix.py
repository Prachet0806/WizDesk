"""Actor-by-action contract for the team (workspace) isolation boundary."""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from tasks.models import Subtask, Task
from users.models import Team, User


class AuthorizationMatrixTests(TestCase):
    def setUp(self):
        cache.clear()
        self.alpha = Team.objects.create(code="ALPHA1", name="Alpha")
        self.beta = Team.objects.create(code="BETA01", name="Beta")
        self.owner = self.user("owner", self.alpha, User.Role.LEADER)
        self.member = self.user("member", self.alpha, User.Role.MEMBER)
        self.pending = self.user(
            "pending", self.alpha, User.Role.MEMBER, User.Status.PENDING
        )
        self.outsider = self.user("outsider", self.beta, User.Role.LEADER)
        self.alpha.leader = self.owner
        self.alpha.save(update_fields=["leader"])
        self.beta.leader = self.outsider
        self.beta.save(update_fields=["leader"])
        self.task = Task.objects.create(
            title="Private alpha task", team=self.alpha, created_by=self.owner
        )
        self.child = Subtask.objects.create(task=self.task, title="Private child")

    def user(self, name, team, role, status=User.Status.APPROVED):
        return User.objects.create_user(
            username=name,
            email=f"{name}@example.com",
            password="BlueRiver!2031",
            name=name,
            team=team,
            role=role,
            status=status,
            email_verified=True,
        )

    def client_for(self, user):
        client = APIClient()
        if user:
            client.credentials(
                HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
            )
        return client

    def test_task_and_subtask_actor_matrix(self):
        task_url = f"/api/tasks/{self.task.pk}/"
        child_url = f"/api/tasks/subtask/{self.child.pk}/"
        cases = (
            ("owner", self.owner, (200, 200, 200, 200)),
            ("member", self.member, (200, 403, 403, 403)),
            ("pending", self.pending, (401, 401, 401, 401)),
            ("outsider", self.outsider, (404, 404, 404, 404)),
            ("anonymous", None, (401, 401, 401, 401)),
        )
        for label, actor, expected in cases:
            with self.subTest(actor=label):
                client = self.client_for(actor)
                self.assertEqual(client.get(task_url).status_code, expected[0])
                self.assertEqual(client.get(child_url).status_code, expected[0])
                self.assertEqual(
                    client.put(task_url, {"title": "Attempt"}, format="json").status_code,
                    expected[1],
                )
                self.assertEqual(
                    client.put(child_url, {"title": "Attempt"}, format="json").status_code,
                    expected[2],
                )
                self.assertEqual(client.delete(task_url).status_code, expected[3])
                if actor == self.owner:
                    self.task = Task.objects.create(
                        title="Private alpha task", team=self.alpha, created_by=self.owner
                    )
                    self.child = Subtask.objects.create(task=self.task, title="Private child")
                    task_url = f"/api/tasks/{self.task.pk}/"
                    child_url = f"/api/tasks/subtask/{self.child.pk}/"
        self.assertEqual(Task.objects.filter(team=self.alpha).count(), 1)

    def test_list_assignment_and_membership_ids_cannot_cross_teams(self):
        outsider = self.client_for(self.outsider)
        for url in (
            f"/api/tasks/team/{self.alpha.code}/",
            f"/api/tasks/team/{self.alpha.code}/status/active/",
            f"/api/tasks/user/{self.member.pk}/subtasks/",
            f"/api/auth/team/{self.alpha.code}/all-members/",
            f"/api/auth/team/{self.alpha.code}/pending-requests/",
            f"/api/performance/team/{self.alpha.code}/",
        ):
            with self.subTest(url=url):
                self.assertIn(outsider.get(url).status_code, (403, 404))
        owner = self.client_for(self.owner)
        self.assertEqual(
            owner.post(
                "/api/auth/approve-member/",
                {"userId": str(self.outsider.pk)},
                format="json",
            ).status_code,
            404,
        )

    def test_stale_token_loses_role_and_membership_immediately(self):
        owner = self.client_for(self.owner)
        member = self.client_for(self.member)
        self.owner.role = User.Role.MEMBER
        self.owner.save(update_fields=["role"])
        self.assertEqual(owner.post("/api/tasks/", {"title": "Denied"}, format="json").status_code, 403)
        self.assertEqual(
            owner.post(
                "/api/auth/approve-member/",
                {"userId": str(self.pending.pk)},
                format="json",
            ).status_code,
            403,
        )
        self.member.team = self.beta
        self.member.save(update_fields=["team"])
        self.assertEqual(member.get(f"/api/tasks/{self.task.pk}/").status_code, 404)
        self.member.status = User.Status.REJECTED
        self.member.save(update_fields=["status"])
        self.assertEqual(member.get("/api/auth/me/").status_code, 401)

    def test_team_code_join_is_pending_until_owner_approval(self):
        applicant = self.client_for(None)
        response = applicant.post(
            "/api/auth/send-member-verification/",
            {
                "name": "New Member",
                "email": "new-member@example.com",
                "password": "BlueRiver!2031",
                "teamCode": self.alpha.code,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        joined = User.objects.get(email="new-member@example.com")
        self.assertEqual(joined.status, User.Status.PENDING)
        self.assertEqual(self.client_for(joined).get("/api/auth/me/").status_code, 401)
        self.assertEqual(
            self.client_for(self.outsider).post(
                "/api/auth/approve-member/",
                {"userId": str(joined.pk)},
                format="json",
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client_for(self.owner).post(
                "/api/auth/approve-member/",
                {"userId": str(joined.pk)},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(self.client_for(joined).get("/api/auth/me/").status_code, 200)

    def test_admin_label_does_not_grant_team_mutation_or_django_staff(self):
        admin_label = self.user("admin-label", self.alpha, User.Role.ADMIN)
        client = self.client_for(admin_label)
        self.assertEqual(client.get(f"/api/tasks/{self.task.pk}/").status_code, 200)
        self.assertEqual(
            client.post("/api/tasks/", {"title": "Forbidden"}, format="json").status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/api/auth/approve-member/",
                {"userId": str(self.pending.pk)},
                format="json",
            ).status_code,
            403,
        )
        self.client.force_login(admin_label)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
