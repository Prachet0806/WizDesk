"""Serve disposable browser fixtures; never connects to the configured project DB."""
import os
import sys
import tempfile
from pathlib import Path
from wsgiref.simple_server import make_server


def main():
    with tempfile.TemporaryDirectory(prefix='wizdesk-browser-') as directory:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'wizdesk_backend'))
        os.environ['TEST_DATABASE_URL'] = 'sqlite:///' + str(Path(directory) / 'browser.sqlite3')
        os.environ['DJANGO_SETTINGS_MODULE'] = 'wizdesk_backend.test_settings'
        import django
        django.setup()
        from django.core.management import call_command
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.core.wsgi import get_wsgi_application
        from django.db import connections
        from users.models import User, Team
        from tasks.models import Task, Subtask
        from django.utils import timezone
        call_command('migrate', verbosity=0)
        team = Team.objects.create(code='BROWSE', name='Browser Test Team')
        accounts = {}
        for name, role in [('leader', 'LEADER'), ('member', 'MEMBER')]:
            accounts[name] = User.objects.create_user(username=name, email=f'{name}@example.com',
                password='OceanWaves!2031', name=name.capitalize(), role=role, status='APPROVED',
                team=team, email_verified=True)
        team.leader = accounts['leader']; team.save()
        former = User.objects.create_user(username='former', email='former@example.com', password='OceanWaves!2031',
            name='Former Member', role='MEMBER', status='REJECTED', email_verified=True)
        historical = Task.objects.create(title='Historical assignment', team=team, created_by=accounts['leader'], status='completed')
        Subtask.objects.create(task=historical, title='Historical completed work', assigned_to=former,
            progress='completed', status='completed', completed_at=timezone.now())
        for index in range(25):
            task = Task.objects.create(title='Duplicate Title' if index < 2 else f'Browser Task {index}',
                team=team, created_by=accounts['leader'])
            Subtask.objects.create(task=task,
                title='<img src=x onerror="window.__xss=true">' if index == 0 else f'Subtask {index}',
                description='</textarea><img src=x onerror="window.__xss=true">' if index == 0 else '',
                assigned_to=accounts['member'], progress='assigned', status='assigned',
                deadline='2030-02-01T04:30:00Z')
        server = make_server('127.0.0.1', 8019, StaticFilesHandler(get_wsgi_application()))
        print('Disposable browser fixtures: http://127.0.0.1:8019 — leader/member@example.com, OceanWaves!2031', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            connections.close_all()


if __name__ == '__main__':
    main()
