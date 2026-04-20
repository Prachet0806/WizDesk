from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db.models import Count, Q
from tasks.models import Task, Subtask
from users.models import User, Team

class IsTeamLeader(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.LEADER)

class TeamPerformanceView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]

    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        team_members = User.objects.filter(
            team__code=team_code, 
            role=User.Role.MEMBER, 
            status=User.Status.APPROVED
        ).annotate(
            assigned_count=Count('assigned_subtasks'),
            completed_count=Count('assigned_subtasks', filter=Q(assigned_subtasks__status='completed')),
            # Active defined as assigned but not completed
            active_count=Count('assigned_subtasks', filter=~Q(assigned_subtasks__status='completed'))
        )
        
        member_stats = []
        for member in team_members:
            assigned = member.assigned_count
            completed = member.completed_count
            rate = round((completed / assigned) * 100) if assigned > 0 else 0
            
            member_stats.append({
                'id': str(member.id),
                'name': member.name,
                'email': member.email,
                'completed_tasks': completed,
                'active_tasks': member.active_count,
                'assigned_tasks': assigned,
                'total_tasks': assigned, # For frontend compatibility
                'completion_rate': rate
            })
            
        return Response(member_stats)
