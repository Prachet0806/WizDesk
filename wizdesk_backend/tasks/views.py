from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, Exists, OuterRef
from .models import Task, Subtask
from .serializers import TaskSerializer, SubtaskSerializer
from users.models import User
import json
import uuid

def clean_priority(value, default='medium'):
    valid = {choice[0] for choice in Task.Priority.choices}
    return value if value in valid else default

class IsTeamMember(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.team)

def _valid_assignee(raw, team):
    if not raw:
        return None
    try:
        uid = uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None
    return User.objects.filter(
        id=uid,
        team=team,
        role=User.Role.MEMBER,
        status=User.Status.APPROVED
    ).first()

class TaskCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def post(self, request):
        team = request.user.team
        title = (request.data.get('title') or '').strip()
        description = request.data.get('description', '')
        subtasks_data = request.data.get('subtasks', [])

        if not team:
            return Response({'error': 'No team associated with your account'}, status=status.HTTP_400_BAD_REQUEST)
        if not title:
            return Response({'error': 'Task title is required'}, status=status.HTTP_400_BAD_REQUEST)

        task = Task.objects.create(
            title=title,
            description=description,
            team=team,
            created_by=request.user,
            status=Task.Status.ACTIVE,
            priority=clean_priority(request.data.get('priority'))
        )

        for st in subtasks_data:
            if st.get('title'):
                assignee = _valid_assignee(st.get('assigned_to'), team)
                subtask = Subtask.objects.create(
                    task=task,
                    title=st['title'],
                    description=st.get('description', ''),
                    assigned_to=assignee,
                    deadline=st.get('deadline'),
                    priority=clean_priority(st.get('priority'))
                )
                if assignee:
                    subtask.status = Subtask.Status.ASSIGNED
                    subtask.progress = Subtask.Progress.ASSIGNED
                    subtask.save()
                    
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

class TeamTasksView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    serializer_class = TaskSerializer
    pagination_class = None

    def get_queryset(self):
        team_code = self.kwargs['team_code']
        return Task.objects.filter(team__code=team_code)\
            .select_related('created_by', 'team')\
            .prefetch_related('subtasks__assigned_to')\
            .order_by('-created_at')

    def list(self, request, *args, **kwargs):
        team_code = self.kwargs['team_code']
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

class TeamTasksStatusView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    serializer_class = TaskSerializer
    pagination_class = None

    def get_queryset(self):
        team_code = self.kwargs['team_code']
        status_val = self.kwargs['status_val'].lower()

        queryset = Task.objects.filter(team__code=team_code)\
            .select_related('created_by', 'team')\
            .prefetch_related('subtasks__assigned_to')\
            .order_by('-created_at')

        non_completed_subtasks = Subtask.objects.filter(
            task=OuterRef('pk')
        ).exclude(progress=Subtask.Progress.COMPLETED)

        if status_val == 'active':
            return queryset.filter(
                Q(status=Task.Status.ACTIVE) & (
                    Q(subtasks__isnull=True) | Exists(non_completed_subtasks)
                )
            ).distinct()
        elif status_val == 'completed':
            return queryset.filter(
                Q(status=Task.Status.COMPLETED, subtasks__isnull=True) |
                (Q(subtasks__isnull=False) & ~Exists(non_completed_subtasks))
            ).distinct()

        return queryset.filter(status__iexact=status_val)

    def list(self, request, *args, **kwargs):
        team_code = self.kwargs['team_code']
        if not request.user.team or request.user.team.code != team_code:
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
        if request.user.role != User.Role.LEADER:
            return Response({'error': 'Only the team leader can update tasks'}, status=status.HTTP_403_FORBIDDEN)
        
        new_status = request.data.get('status')
        title = request.data.get('title')
        description = request.data.get('description')
        priority = request.data.get('priority')
        
        if new_status:
            task.status = new_status.upper() if new_status.upper() in dict(Task.Status.choices) else new_status.lower()
        if title:
            task.title = title
        if description is not None:
            task.description = description
        if priority:
            task.priority = clean_priority(priority, task.priority)
            
        task.save()
        return Response({'message': 'Task updated successfully', 'task': TaskSerializer(task).data})

    def delete(self, request, task_id):
        task = self.get_object(task_id, request)
        if not task: return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role != User.Role.LEADER:
            return Response({'error': 'Only the team leader can delete tasks'}, status=status.HTTP_403_FORBIDDEN)
        task.delete()
        return Response({'message': 'Task deleted successfully'})

class UserAssignedSubtasksView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def get(self, request, user_id):
        if str(request.user.id) != str(user_id) and request.user.role != User.Role.LEADER:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        subtasks = Subtask.objects.filter(
            assigned_to_id=user_id,
            task__team=request.user.team
        ).select_related('task').order_by('-created_at')
        
        # Serialize but include task title and description dynamically
        data = []
        for s in subtasks:
            s_data = SubtaskSerializer(s).data
            s_data['task_title'] = s.task.title
            s_data['task_description'] = s.task.description
            s_data['task_id'] = s.task.id
            data.append(s_data)
        return Response(data)

class TakeSubtaskView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def post(self, request, subtask_id):
        try:
            subtask = Subtask.objects.get(id=subtask_id, task__team=request.user.team)
        except Subtask.DoesNotExist:
            return Response({'error': 'Subtask not found'}, status=status.HTTP_404_NOT_FOUND)

        if subtask.progress == Subtask.Progress.COMPLETED:
            return Response({'error': 'Subtask is already completed'}, status=status.HTTP_400_BAD_REQUEST)
        if subtask.assigned_to_id and str(subtask.assigned_to_id) != str(request.user.id):
            return Response({'error': 'Subtask is assigned to another member'}, status=status.HTTP_400_BAD_REQUEST)

        subtask.assigned_to = request.user
        subtask.progress = Subtask.Progress.IN_PROGRESS
        subtask.status = Subtask.Status.TAKEN
        subtask.sync_state()
        return Response({'message': 'Subtask taken successfully', 'subtask': SubtaskSerializer(subtask).data})

class UpdateSubtaskProgressView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def post(self, request, subtask_id):
        try:
            subtask = Subtask.objects.get(id=subtask_id, task__team=request.user.team)
        except Subtask.DoesNotExist:
            return Response({'error': 'Subtask not found'}, status=status.HTTP_404_NOT_FOUND)

        if str(subtask.assigned_to_id) != str(request.user.id) and request.user.role != User.Role.LEADER:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        new_progress = request.data.get('progress')
        if new_progress:
            new_progress = new_progress.lower()
            if new_progress not in dict(Subtask.Progress.choices):
                return Response({'error': 'Invalid progress value'}, status=status.HTTP_400_BAD_REQUEST)
            subtask.progress = new_progress
            subtask.sync_state()
        return Response({'message': 'Progress updated successfully', 'subtask': SubtaskSerializer(subtask).data})

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
        if request.user.role != User.Role.LEADER:
            return Response({'error': 'Only the team leader can update subtasks'}, status=status.HTTP_403_FORBIDDEN)
        
        title = request.data.get('title')
        description = request.data.get('description')
        
        if title:
            subtask.title = title
        if description is not None:
            subtask.description = description
        
        if 'deadline' in request.data:
            subtask.deadline = request.data.get('deadline') or None

        if 'priority' in request.data:
            subtask.priority = clean_priority(request.data.get('priority'), subtask.priority)
            
        if 'assigned_to' in request.data:
            assigned_to = request.data.get('assigned_to')
            if assigned_to:
                assignee = _valid_assignee(assigned_to, request.user.team)
                if not assignee:
                    return Response({'error': 'Assignee must be an approved member of your team'}, status=status.HTTP_400_BAD_REQUEST)
                subtask.assigned_to = assignee
                if subtask.progress == Subtask.Progress.NOT_STARTED:
                    subtask.progress = Subtask.Progress.ASSIGNED
            else:
                subtask.assigned_to = None
                subtask.progress = Subtask.Progress.NOT_STARTED
            
        subtask.sync_state()
        return Response({'message': 'Subtask updated successfully', 'subtask': SubtaskSerializer(subtask).data})

    def delete(self, request, subtask_id):
        subtask = self.get_object(subtask_id, request)
        if not subtask: return Response({'error': 'Subtask not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role != User.Role.LEADER:
            return Response({'error': 'Only the team leader can delete subtasks'}, status=status.HTTP_403_FORBIDDEN)
        subtask.delete()
        return Response({'message': 'Subtask deleted successfully'})
