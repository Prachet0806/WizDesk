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
        if request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        team_members = User.objects.filter(team__code=team_code, role=User.Role.MEMBER, status=User.Status.APPROVED)
        
        member_stats = []
        for member in team_members:
            assigned = Subtask.objects.filter(assigned_to=member)
            m_completed = assigned.filter(status=Subtask.Status.COMPLETED).count()
            m_active = assigned.exclude(status=Subtask.Status.COMPLETED).count()
            member_stats.append({
                'id': str(member.id),
                'name': member.name,
                'email': member.email,
                'completed_tasks': m_completed,
                'active_tasks': m_active,
                'assigned_tasks': assigned.count()
            })
            
        return Response(member_stats)
