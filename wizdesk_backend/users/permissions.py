from django.conf import settings
from rest_framework.permissions import BasePermission
from .models import User


def eligible(user):
    return bool(user and user.is_authenticated and user.is_active
                and user.status == User.Status.APPROVED and user.team_id
                and (not settings.EMAIL_VERIFICATION_REQUIRED or user.email_verified))


class IsApprovedTeamMember(BasePermission):
    message = 'An approved, verified team membership is required.'

    def has_permission(self, request, view):
        return eligible(request.user)


class IsTeamLeader(IsApprovedTeamMember):
    def has_permission(self, request, view):
        user = request.user
        return eligible(user) and user.role == User.Role.LEADER and user.team.leader_id == user.pk
