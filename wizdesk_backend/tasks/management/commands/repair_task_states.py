"""Audit first; apply only deterministic repairs after reviewing a backup."""
from django.core.management.base import BaseCommand
from django.db import transaction
from tasks.models import Task, Subtask
from tasks.services import refresh_parent


class Command(BaseCommand):
    help = 'Report task-state drift; --apply repairs deterministic cases. Never guesses historical timestamps.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        changed = ambiguous = 0
        for task_id in Task.objects.order_by('pk').values_list('pk', flat=True).iterator():
            with transaction.atomic():
                task = Task.objects.select_for_update().get(pk=task_id)
                children = list(task.subtasks.select_for_update(of=('self',)).select_related('assigned_to').order_by('pk'))
                if task.status not in Task.Status.values:
                    self.stdout.write(f'Ambiguous task status: {task.pk}')
                    ambiguous += 1
                    continue
                if task.priority not in Task.Priority.values:
                    self.stdout.write(f'Ambiguous task priority: {task.pk}')
                    ambiguous += 1
                valid = True
                for child in children:
                    if child.priority not in Subtask.Priority.values:
                        self.stdout.write(f'Ambiguous subtask priority: {child.pk}')
                        ambiguous += 1
                    if child.progress not in Subtask.Progress.values or (child.progress == 'completed' and child.completed_at is None):
                        self.stdout.write(f'Ambiguous progress or completion time: {child.pk}')
                        ambiguous += 1; valid = False
                        continue
                    progress = child.progress
                    completed_at = child.completed_at
                    assignee = child.assigned_to
                    if progress != 'completed' and assignee and (assignee.team_id != task.team_id or
                            assignee.status != 'APPROVED' or assignee.role != 'MEMBER' or not assignee.is_active):
                        assignee = None
                    if progress == 'completed':
                        status = 'completed'
                    elif assignee is None:
                        progress, status, completed_at = 'not_started', 'available', None
                    elif progress in ('not_started', 'assigned'):
                        progress, status, completed_at = 'assigned', 'assigned', None
                    else:
                        status, completed_at = 'taken', None
                    if (progress, status, completed_at, assignee) != (child.progress, child.status, child.completed_at, child.assigned_to):
                        changed += 1
                        self.stdout.write(f'Subtask state drift: {child.pk}')
                        if options['apply']:
                            child.progress, child.status, child.completed_at = progress, status, completed_at
                            child.assigned_to = assignee
                            child.save(update_fields=['progress', 'status', 'completed_at', 'assigned_to'])
                if valid and children and task.status != 'archived':
                    derived = 'completed' if all(s.progress == 'completed' for s in children) else 'active'
                    if task.status != derived:
                        changed += 1
                        self.stdout.write(f'Task state drift: {task.pk}')
                        if options['apply']: refresh_parent(task)
        mode = 'Applied' if options['apply'] else 'Dry run'
        self.stdout.write(f'{mode}: {changed} deterministic repairs; {ambiguous} ambiguous records require review.')
        self.stdout.write('Historical deadline timezone offsets cannot be inferred from stored UTC values.')
