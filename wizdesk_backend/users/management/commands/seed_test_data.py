"""
Management command: python manage.py seed_test_data

Creates default test credentials:
  Leader:    rohan@gmail.com / 123
  Team code: E87HPQ
  Team name: Rohan's Team

Run any time to re-create the test data (safe to re-run — idempotent).
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from users.models import User, Team


class Command(BaseCommand):
    help = 'Seeds test data: leader rohan@gmail.com / 123 with team code E87HPQ'

    def handle(self, *args, **options):
        with transaction.atomic():
            # ── Team ──────────────────────────────────────────────────────────
            team, team_created = Team.objects.get_or_create(
                code='E87HPQ',
                defaults={'name': "Rohan's Team"}
            )
            self.stdout.write(f"Team {'created' if team_created else 'already exists'}: {team.name} ({team.code})")

            # ── Leader ────────────────────────────────────────────────────────
            leader, user_created = User.objects.get_or_create(
                email='rohan@gmail.com',
                defaults={
                    'username': 'rohan@gmail.com',
                    'name': 'Rohan',
                    'role': User.Role.LEADER,
                    'status': User.Status.APPROVED,
                    'email_verified': True,
                    'team': team,
                    'team_name': team.name,
                }
            )
            leader.set_password('123')
            leader.save()

            # Ensure the team points back to the leader
            if not team.leader:
                team.leader = leader
                team.save()

            self.stdout.write(f"Leader {'created' if user_created else 'updated'}: rohan@gmail.com / 123")

            self.stdout.write(self.style.SUCCESS(
                '\n✅ Test data ready!\n'
                '   Email:     rohan@gmail.com\n'
                '   Password:  123\n'
                '   Team code: E87HPQ\n'
            ))
