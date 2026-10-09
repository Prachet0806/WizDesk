from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied, APIException
from django.shortcuts import get_object_or_404
from users.models import User
from users.permissions import eligible
from .models import Task, Subtask


class Conflict(APIException):
    status_code = 409
    default_detail = 'This record changed. Reload before trying again.'


def lock_actor(user):
    current = User.objects.select_for_update(of=('self',)).select_related('team').get(pk=user.pk)
    if not eligible(current):
        raise PermissionDenied('Your membership is no longer eligible.')
    return current


def lock_assignees(values, team):
    ids = {value['assigned_to'].pk for value in values if value.get('assigned_to')}
    found = {u.pk: u for u in User.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
    for uid in ids:
        u = found.get(uid)
        if not u or u.role != User.Role.MEMBER or u.team_id != team.pk or not eligible(u):
            raise ValidationError({'assigned_to': 'Assignee is no longer an approved team member.'})


def set_subtask_state(subtask):
    if subtask.progress == Subtask.Progress.COMPLETED:
        subtask.status = Subtask.Status.COMPLETED
        subtask.completed_at = subtask.completed_at or timezone.now()
    else:
        subtask.completed_at = None
        if not subtask.assigned_to_id:
            subtask.progress = Subtask.Progress.NOT_STARTED
            subtask.status = Subtask.Status.AVAILABLE
        elif subtask.progress in (Subtask.Progress.NOT_STARTED, Subtask.Progress.ASSIGNED):
            subtask.progress = Subtask.Progress.ASSIGNED
            subtask.status = Subtask.Status.ASSIGNED
        else:
            subtask.status = Subtask.Status.TAKEN


def refresh_parent(task):
    children = task.subtasks.all()
    if task.status != Task.Status.ARCHIVED:
        if children.exists():
            task.status = Task.Status.ACTIVE if children.exclude(progress=Subtask.Progress.COMPLETED).exists() else Task.Status.COMPLETED
        elif task.status == Task.Status.COMPLETED:
            # Preserve explicit completion for tasks without subtasks.
            task.status = Task.Status.COMPLETED
        else:
            task.status = Task.Status.ACTIVE
    task.save(update_fields=['status', 'updated_at'])


@transaction.atomic
def release_unfinished(member, team):
    task_ids = list(Subtask.objects.filter(assigned_to=member, task__team=team)
                    .exclude(progress=Subtask.Progress.COMPLETED).values_list('task_id', flat=True))
    for task in Task.objects.select_for_update().filter(pk__in=task_ids).order_by('pk'):
        for child in task.subtasks.filter(assigned_to=member).exclude(progress=Subtask.Progress.COMPLETED):
            child.assigned_to = None
            set_subtask_state(child)
            child.save()
        refresh_parent(task)


@transaction.atomic
def save_task(actor, values, task_id=None):
    actor = lock_actor(actor)
    if actor.role != User.Role.LEADER or actor.team.leader_id != actor.pk:
        raise PermissionDenied('Only the team leader can manage tasks.')
    values = dict(values)
    children = values.pop('subtasks', [])
    deleted = values.pop('deleted_subtask_ids', [])
    expected = values.pop('expected_updated_at', None)
    lock_assignees(children, actor.team)
    if task_id:
        task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, team=actor.team)
        if expected is not None and task.updated_at != expected:
            raise Conflict()
        known = set(task.subtasks.values_list('pk', flat=True))
        referenced = set(deleted) | {s['id'] for s in children if s.get('id')}
        if not referenced <= known:
            raise ValidationError({'subtasks': 'All subtask IDs must belong to this task.'})
    else:
        task = Task(team=actor.team, created_by=actor)
    for key, value in values.items():
        if key == 'priority' and value is None:
            continue
        setattr(task, key, value)
    task.save()
    task.subtasks.filter(pk__in=deleted).delete()
    for data in children:
        data = dict(data)
        uid = data.pop('id', None)
        child = task.subtasks.get(pk=uid) if uid else Subtask(task=task)
        for key, value in data.items():
            if key == 'priority' and value is None:
                continue
            setattr(child, key, value)
        if 'assigned_to' in data and data['assigned_to'] is None:
            child.progress = Subtask.Progress.NOT_STARTED
        set_subtask_state(child)
        child.save()
    if values.get('status') == Task.Status.COMPLETED and task.subtasks.exclude(progress=Subtask.Progress.COMPLETED).exists():
        raise ValidationError({'status': 'Complete all subtasks before completing the task.'})
    refresh_parent(task)
    return task
