"""Create explicit demo credentials in development without replacing accounts."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from users.models import User, Team


class Command(BaseCommand):
    help = 'Create a development-only example.com leader with explicit credentials.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--password', required=True)
        parser.add_argument('--team-code', required=True)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Demo seeding requires DEBUG=True; production seeding is disabled.')
        email = options['email'].lower()
        if not email.endswith('@example.com'):
            raise CommandError('Use an example.com email address for demo accounts.')
        try:
            validate_password(options['password'], User(email=email, username=email))
        except ValidationError as exc:
            raise CommandError(' '.join(exc.messages)) from exc
        with transaction.atomic():
            if User.objects.filter(email__iexact=email).exists() or Team.objects.filter(code=options['team_code']).exists():
                raise CommandError('Account or team already exists; no existing credentials were changed.')
            user = User.objects.create_user(username=email, email=email, password=options['password'],
                name='Demo Leader', role=User.Role.LEADER, status=User.Status.APPROVED, email_verified=True)
            team = Team.objects.create(code=options['team_code'], name='Demo Team', leader=user)
            user.team = team
            user.save(update_fields=['team'])
        self.stdout.write(self.style.SUCCESS('Demo account and team created.'))
