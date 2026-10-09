from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.response import Response
from users.api import ObjectAPIView as APIView
from rest_framework.exceptions import ValidationError, PermissionDenied
from users.models import User
from users.permissions import IsApprovedTeamMember, IsTeamLeader
from .models import Task, Subtask
from .serializers import TaskSerializer, SubtaskSerializer, TaskInputSerializer, SubtaskInputSerializer
from .services import save_task, lock_actor, lock_assignees, refresh_parent, set_subtask_state, Conflict


class TaskCreateView(APIView):
    permission_classes = [IsTeamLeader]
    throttle_scope = 'mutation'

    def post(self, request):
        serializer = TaskInputSerializer(data=request.data, context={'team': request.user.team})
        serializer.is_valid(raise_exception=True)
        task = save_task(request.user, serializer.validated_data)
        return Response(TaskSerializer(task).data, status=201)


class TeamTasksView(generics.ListAPIView):
    permission_classes = [IsApprovedTeamMember]
    serializer_class = TaskSerializer

    def get_queryset(self):
        if self.request.user.team.code != self.kwargs['team_code']:
            raise PermissionDenied('Unauthorized')
        qs = Task.objects.filter(team=self.request.user.team).select_related('created_by', 'team').prefetch_related('subtasks__assigned_to').order_by('-created_at', '-pk')
        if self.request.query_params.get('search'):
            qs = qs.filter(title__icontains=self.request.query_params['search'][:255])
        return qs


class TeamTasksStatusView(TeamTasksView):
    def get_queryset(self):
        value = self.kwargs['status_val'].lower()
        if value not in Task.Status.values:
            raise ValidationError({'status': 'Invalid task status.'})
        return super().get_queryset().filter(status=value)


class TaskDetailView(APIView):
    permission_classes = [IsApprovedTeamMember]
    throttle_scope = 'mutation'

    def get(self, request, task_id):
        task = get_object_or_404(Task, pk=task_id, team=request.user.team)
        return Response(TaskSerializer(task).data)

    def put(self, request, task_id):
        task = get_object_or_404(Task, pk=task_id, team=request.user.team)
        serializer = TaskInputSerializer(data=request.data, context={'team': request.user.team, 'updating': True, 'priority_default': task.priority})
        serializer.is_valid(raise_exception=True)
        task = save_task(request.user, serializer.validated_data, task_id)
        return Response({'message': 'Task updated successfully', 'task': TaskSerializer(task).data})

    patch = put

    @transaction.atomic
    def delete(self, request, task_id):
        actor = lock_actor(request.user)
        if actor.role != User.Role.LEADER or actor.team.leader_id != actor.pk:
            raise PermissionDenied('Only the team leader can delete tasks.')
        task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, team=actor.team)
        task.delete()
        return Response({'message': 'Task deleted successfully'})


class UserAssignedSubtasksView(generics.ListAPIView):
    permission_classes = [IsApprovedTeamMember]
    serializer_class = SubtaskSerializer

    def get_queryset(self):
        user = self.request.user
        if user.pk != self.kwargs['user_id'] and not (user.role == User.Role.LEADER and user.team.leader_id == user.pk):
            raise PermissionDenied('Unauthorized')
        return Subtask.objects.filter(assigned_to_id=self.kwargs['user_id'], task__team=user.team).select_related('task', 'assigned_to').order_by('-created_at', '-pk')


def locked_subtask(actor, subtask_id):
    # Parent-first locking is shared with aggregate edits and all state changes.
    snapshot = get_object_or_404(Subtask, pk=subtask_id, task__team=actor.team)
    parent = Task.objects.select_for_update().get(pk=snapshot.task_id)
    if parent.status == Task.Status.ARCHIVED:
        raise ValidationError('Unarchive the task before changing its subtasks.')
    child = get_object_or_404(Subtask.objects.select_for_update(), pk=subtask_id, task=parent)
    child.task = parent
    return child


class TakeSubtaskView(APIView):
    permission_classes = [IsApprovedTeamMember]
    throttle_scope = 'mutation'

    @transaction.atomic
    def post(self, request, subtask_id):
        actor = lock_actor(request.user)
        if actor.role != User.Role.MEMBER:
            raise PermissionDenied('Only members can claim subtasks.')
        child = locked_subtask(actor, subtask_id)
        if child.progress == Subtask.Progress.COMPLETED:
            raise ValidationError('Subtask is already completed.')
        if child.assigned_to_id and child.assigned_to_id != actor.pk:
            raise Conflict('Subtask is assigned to another member.')
        child.assigned_to = actor
        child.progress = Subtask.Progress.IN_PROGRESS
        child.sync_state()
        return Response({'message': 'Subtask taken successfully', 'subtask': SubtaskSerializer(child).data})


class UpdateSubtaskProgressView(APIView):
    permission_classes = [IsApprovedTeamMember]
    throttle_scope = 'mutation'

    @transaction.atomic
    def post(self, request, subtask_id):
        actor = lock_actor(request.user)
        child = locked_subtask(actor, subtask_id)
        if child.assigned_to_id != actor.pk and not (actor.role == User.Role.LEADER and actor.team.leader_id == actor.pk):
            raise PermissionDenied('Unauthorized')
        progress = request.data.get('progress')
        if progress not in Subtask.Progress.values:
            raise ValidationError({'progress': 'Invalid progress value.'})
        if progress != Subtask.Progress.NOT_STARTED and not child.assigned_to_id:
            raise ValidationError('Assign the subtask before reporting progress.')
        child.progress = progress
        child.sync_state()
        return Response({'message': 'Progress updated successfully', 'subtask': SubtaskSerializer(child).data})


class SubtaskDetailView(APIView):
    permission_classes = [IsApprovedTeamMember]
    throttle_scope = 'mutation'

    def get(self, request, subtask_id):
        child = get_object_or_404(Subtask.objects.select_related('task', 'assigned_to'), pk=subtask_id, task__team=request.user.team)
        return Response(SubtaskSerializer(child).data)

    @transaction.atomic
    def put(self, request, subtask_id):
        actor = lock_actor(request.user)
        if actor.role != User.Role.LEADER or actor.team.leader_id != actor.pk:
            raise PermissionDenied('Only the team leader can update subtasks.')
        snapshot = get_object_or_404(Subtask, pk=subtask_id, task__team=actor.team)
        serializer = SubtaskInputSerializer(data=request.data, context={'team': actor.team, 'priority_default': snapshot.priority})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop('id', None)
        lock_assignees([data], actor.team)
        child = locked_subtask(actor, subtask_id)
        for key, value in data.items():
            if key == 'priority' and value is None:
                continue
            setattr(child, key, value)
        if 'assigned_to' in data and data['assigned_to'] is None:
            child.progress = Subtask.Progress.NOT_STARTED
        child.sync_state()
        return Response({'message': 'Subtask updated successfully', 'subtask': SubtaskSerializer(child).data})

    patch = put

    @transaction.atomic
    def delete(self, request, subtask_id):
        actor = lock_actor(request.user)
        if actor.role != User.Role.LEADER or actor.team.leader_id != actor.pk:
            raise PermissionDenied('Only the team leader can delete subtasks.')
        child = locked_subtask(actor, subtask_id)
        parent = child.task
        child.delete()
        refresh_parent(parent)
        return Response({'message': 'Subtask deleted successfully'})
