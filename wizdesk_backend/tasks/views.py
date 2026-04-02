from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.settings import api_settings
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Count, Q
from .models import Task, Subtask
from .serializers import TaskSerializer, SubtaskSerializer
from users.models import Team, User
import json

# ── Progress state machine ─────────────────────────────────────────────────
VALID_PROGRESS_TRANSITIONS = {
    'not_started': ['in_progress'],
    'assigned':    ['in_progress'],
    'in_progress': ['testing', 'completed'],
    'testing':     ['in_progress', 'completed'],
    'completed':   [],  # Terminal state
}

class IsTeamMember(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.team)

class TaskCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def post(self, request):
        team_code = request.data.get('teamCode')
        title = (request.data.get('title') or '').strip()
        description = request.data.get('description', '')
        subtasks_data = request.data.get('subtasks', [])

        # ── Validation ──────────────────────────────────────────────────────
        if not title:
            return Response({'error': 'Task title is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Filter out empty subtasks, then check at least one remains
        valid_subtasks = [s for s in subtasks_data if (s.get('title') or '').strip()]
        if not valid_subtasks:
            return Response({'error': 'At least one subtask with a title is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Get team: use request data if provided, otherwise fallback to the user's team
        if team_code:
            try:
                team = Team.objects.get(code=team_code)
            except Team.DoesNotExist:
                return Response({'error': 'Team not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            team = request.user.team

        if not team:
            return Response({'error': 'No team context provided.'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify leader belongs to this team
        if request.user.team != team:
            return Response({'error': 'Unauthorized: you do not belong to this team.'}, status=status.HTTP_403_FORBIDDEN)

        task = Task.objects.create(
            title=title,
            description=description,
            team=team,
            created_by=request.user,
            status=Task.Status.ACTIVE
        )

        # Collect valid assignee IDs for cross-team check
        team_member_ids = set(
            str(uid) for uid in
            User.objects.filter(team=team, status=User.Status.APPROVED).values_list('id', flat=True)
        )

        for st in valid_subtasks:
            assigned_to_id = st.get('assigned_to')
            # Reject cross-team assignment
            if assigned_to_id and str(assigned_to_id) not in team_member_ids:
                task.delete()
                return Response(
                    {'error': f'Assigned user is not a member of this team.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            subtask = Subtask.objects.create(
                task=task,
                title=st['title'].strip(),
                description=st.get('description', ''),
                assigned_to_id=assigned_to_id or None,
                priority=st.get('priority', Subtask.Priority.MEDIUM),
                deadline=st.get('deadline') or None,
            )
            if subtask.assigned_to_id:
                subtask.status = Subtask.Status.ASSIGNED
                subtask.progress = Subtask.Progress.ASSIGNED
                subtask.save()

        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

class TeamTasksView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    serializer_class = TaskSerializer

    def get_queryset(self):
        team_code = self.kwargs['team_code']
        return Task.objects.filter(team__code=team_code)\
            .select_related('created_by', 'team')\
            .prefetch_related('subtasks__assigned_to')\
            .order_by('-created_at')

    def list(self, request, *args, **kwargs):
        team_code = self.kwargs['team_code']
        if request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

class TeamTasksStatusView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    serializer_class = TaskSerializer

    def get_queryset(self):
        team_code = self.kwargs['team_code']
        status_val = self.kwargs['status_val'].lower()

        queryset = Task.objects.filter(team__code=team_code)\
            .select_related('created_by', 'team')\
            .prefetch_related('subtasks__assigned_to')\
            .order_by('-created_at')

        if status_val == 'active':
            # Active tasks: status is ACTIVE and at least one subtask is not completed
            return queryset.filter(
                status=Task.Status.ACTIVE
            ).filter(
                subtasks__status__in=['available', 'assigned', 'taken']
            ).distinct()
        elif status_val == 'completed':
            # Completed tasks: status is COMPLETED OR all subtasks are completed
            return queryset.annotate(
                total_st=Count('subtasks'),
                completed_st=Count('subtasks', filter=Q(subtasks__status='completed'))
            ).filter(
                Q(status=Task.Status.COMPLETED) |
                Q(total_st__gt=0, total_st=F('completed_st'))
            ).distinct()

        return queryset.filter(status__iexact=status_val)

    def list(self, request, *args, **kwargs):
        team_code = self.kwargs['team_code']
        if request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

class TaskDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]

    def get_object(self, task_id, request):
        try:
            return Task.objects.get(id=task_id, team=request.user.team)
        except Task.DoesNotExist:
            return None

    def get(self, request, task_id):
        task = self.get_object(task_id, request)
        if not task: return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(TaskSerializer(task).data)

    def put(self, request, task_id):
        task = self.get_object(task_id, request)
        if not task: return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        title = request.data.get('title')
        description = request.data.get('description')

        if new_status:
            task.status = new_status.upper() if new_status.upper() in dict(Task.Status.choices) else new_status.lower()
        if title:
            task.title = title
        if description is not None:
            task.description = description

        task.save()
        return Response({'message': 'Task updated successfully', 'task': TaskSerializer(task).data})

    def delete(self, request, task_id):
        task = self.get_object(task_id, request)
        if not task: return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        task.delete()
        return Response({'message': 'Task deleted successfully'})


class UserAssignedSubtasksView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def get(self, request, user_id):
        if str(request.user.id) != str(user_id) and request.user.role != User.Role.LEADER:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        subtasks = Subtask.objects.filter(assigned_to_id=user_id).select_related('task').order_by('-created_at')

        paginator = api_settings.DEFAULT_PAGINATION_CLASS()
        paginated_subtasks = paginator.paginate_queryset(subtasks, request)

        data = []
        for s in paginated_subtasks:
            s_data = SubtaskSerializer(s).data
            s_data['task_title'] = s.task.title
            s_data['task_description'] = s.task.description
            s_data['task_id'] = s.task.id
            data.append(s_data)
        return paginator.get_paginated_response(data)

class TakeSubtaskView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def post(self, request, subtask_id):
        try:
            with transaction.atomic():
                # select_for_update locks the row so concurrent requests can't double-take
                subtask = Subtask.objects.select_for_update().get(
                    id=subtask_id,
                    task__team=request.user.team,
                    status=Subtask.Status.AVAILABLE  # Only AVAILABLE subtasks can be taken
                )
                subtask.assigned_to = request.user
                subtask.status = Subtask.Status.TAKEN
                subtask.progress = Subtask.Progress.IN_PROGRESS
                subtask.save()
                return Response({'message': 'Subtask taken successfully', 'subtask': SubtaskSerializer(subtask).data})
        except Subtask.DoesNotExist:
            return Response(
                {'error': 'Subtask not found or already taken by another member.'},
                status=status.HTTP_404_NOT_FOUND
            )

class UpdateSubtaskProgressView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def post(self, request, subtask_id):
        try:
            subtask = Subtask.objects.get(id=subtask_id, task__team=request.user.team)
            if str(subtask.assigned_to_id) != str(request.user.id) and request.user.role != User.Role.LEADER:
                return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

            new_progress = request.data.get('progress')
            if not new_progress:
                return Response({'error': 'progress field is required.'}, status=status.HTTP_400_BAD_REQUEST)

            # ── State machine validation ─────────────────────────────────
            current = subtask.progress
            allowed = VALID_PROGRESS_TRANSITIONS.get(current, [])
            if new_progress not in allowed:
                return Response(
                    {'error': f"Invalid transition: '{current}' → '{new_progress}'. Allowed next states: {allowed}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            subtask.progress = new_progress
            if new_progress == Subtask.Progress.COMPLETED:
                subtask.status = Subtask.Status.COMPLETED
                subtask.completed_at = timezone.now()

                # Sync parent task status: mark COMPLETED if all subtasks done
                parent_task = subtask.task
                # Save subtask first so the exclude query sees the latest state
                subtask.save()
                if not parent_task.subtasks.exclude(status=Subtask.Status.COMPLETED).exists():
                    parent_task.status = Task.Status.COMPLETED
                    parent_task.save()
                return Response({'message': 'Progress updated successfully', 'subtask': SubtaskSerializer(subtask).data})

            subtask.save()
            return Response({'message': 'Progress updated successfully', 'subtask': SubtaskSerializer(subtask).data})
        except Subtask.DoesNotExist:
            return Response({'error': 'Subtask not found'}, status=status.HTTP_404_NOT_FOUND)

class SubtaskDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]

    def get_object(self, subtask_id, request):
        try:
            return Subtask.objects.get(id=subtask_id, task__team=request.user.team)
        except Subtask.DoesNotExist:
            return None

    def get(self, request, subtask_id):
        subtask = self.get_object(subtask_id, request)
        if not subtask: return Response({'error': 'Subtask not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(SubtaskSerializer(subtask).data)

    def put(self, request, subtask_id):
        subtask = self.get_object(subtask_id, request)
        if not subtask: return Response({'error': 'Subtask not found'}, status=status.HTTP_404_NOT_FOUND)

        title = request.data.get('title')
        description = request.data.get('description')

        if title:
            subtask.title = title
        if description is not None:
            subtask.description = description

        if 'priority' in request.data:
            subtask.priority = request.data.get('priority') or Subtask.Priority.MEDIUM

        if 'deadline' in request.data:
            subtask.deadline = request.data.get('deadline') or None

        if 'assigned_to' in request.data:
            assigned_to = request.data.get('assigned_to')
            if assigned_to:
                subtask.assigned_to_id = assigned_to
                if subtask.status == Subtask.Status.AVAILABLE:
                    subtask.status = Subtask.Status.ASSIGNED
                    subtask.progress = Subtask.Progress.ASSIGNED
            else:
                subtask.assigned_to_id = None

        subtask.save()
        return Response({'message': 'Subtask updated successfully', 'subtask': SubtaskSerializer(subtask).data})

    def delete(self, request, subtask_id):
        subtask = self.get_object(subtask_id, request)
        if not subtask: return Response({'error': 'Subtask not found'}, status=status.HTTP_404_NOT_FOUND)
        subtask.delete()
        return Response({'message': 'Subtask deleted successfully'})
