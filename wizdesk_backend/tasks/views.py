from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from .models import Task, Subtask
from .serializers import TaskSerializer, SubtaskSerializer
from users.models import Team, User
import json

class IsTeamMember(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.team)

class TaskCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def post(self, request):
        team_code = request.data.get('teamCode')
        title = request.data.get('title')
        description = request.data.get('description', '')
        subtasks_data = request.data.get('subtasks', [])

        try:
            team = Team.objects.get(code=team_code)
        except Team.DoesNotExist:
            return Response({'error': 'Team not found'}, status=status.HTTP_404_NOT_FOUND)

        task = Task.objects.create(
            title=title,
            description=description,
            team=team,
            created_by=request.user,
            status=Task.Status.ACTIVE
        )

        for st in subtasks_data:
            if st.get('title'):
                subtask = Subtask.objects.create(
                    task=task,
                    title=st['title'],
                    description=st.get('description', ''),
                    assigned_to_id=st.get('assigned_to')
                )
                if subtask.assigned_to_id:
                    subtask.status = Subtask.Status.ASSIGNED
                    subtask.progress = Subtask.Progress.ASSIGNED
                    subtask.save()
                    
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

class TeamTasksView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def get(self, request, team_code):
        if request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        tasks = Task.objects.filter(team__code=team_code).order_by('-created_at')
        return Response(TaskSerializer(tasks, many=True).data)

class TeamTasksStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def get(self, request, team_code, status_val):
        if request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        tasks = Task.objects.filter(team__code=team_code, status__iexact=status_val).order_by('-created_at')
        return Response(TaskSerializer(tasks, many=True).data)

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
        # Serialize but include task title dynamically
        data = []
        for s in subtasks:
            s_data = SubtaskSerializer(s).data
            s_data['task_title'] = s.task.title
            # Make sure id vs task_id matches what frontend expects 
            s_data['task_id'] = s.task.id
            data.append(s_data)
        return Response(data)

class TakeSubtaskView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def post(self, request, subtask_id):
        try:
            subtask = Subtask.objects.get(id=subtask_id, task__team=request.user.team)
            subtask.assigned_to = request.user
            subtask.status = Subtask.Status.TAKEN
            subtask.progress = Subtask.Progress.IN_PROGRESS
            subtask.save()
            return Response({'message': 'Subtask taken successfully', 'subtask': SubtaskSerializer(subtask).data})
        except Subtask.DoesNotExist:
            return Response({'error': 'Subtask not found'}, status=status.HTTP_404_NOT_FOUND)

class UpdateSubtaskProgressView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamMember]
    def post(self, request, subtask_id):
        try:
            subtask = Subtask.objects.get(id=subtask_id, task__team=request.user.team)
            if str(subtask.assigned_to_id) != str(request.user.id) and request.user.role != User.Role.LEADER:
                return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
            
            new_progress = request.data.get('progress')
            if new_progress:
                subtask.progress = new_progress
                if new_progress == Subtask.Progress.COMPLETED:
                    subtask.status = Subtask.Status.COMPLETED
                    subtask.completed_at = timezone.now()
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
