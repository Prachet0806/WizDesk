from django.urls import path
from .views import (
    SendLeaderVerificationView,
    VerifyLeaderEmailView,
    SendMemberVerificationView,
    VerifyMemberEmailView,
    LoginView,
    CheckMemberStatusView,
    TeamAllMembersView,
    TeamApprovedMembersView,
    TeamPendingRequestsView,
    TeamRejectedMembersView,
    ApproveMemberView,
    RejectMemberView,
    ApproveRejectedMemberView,
    DeleteRejectedMemberView,
    RemoveTeamMemberView,
    MeView,
)

urlpatterns = [
    # Auth & Verification
    path('send-verification/', SendLeaderVerificationView.as_view(), name='send-verification'),
    path('verify-email/', VerifyLeaderEmailView.as_view(), name='verify-email'),
    path('send-member-verification/', SendMemberVerificationView.as_view(), name='send-member-verification'),
    path('verify-member-email/', VerifyMemberEmailView.as_view(), name='verify-member-email'),
    path('login/', LoginView.as_view(), name='login'),
    path('check-member-status/', CheckMemberStatusView.as_view(), name='check-member-status'),
    path('me/', MeView.as_view(), name='me'),

    # Team Lists
    path('team/<str:team_code>/all-members/', TeamAllMembersView.as_view(), name='team-all-members'),
    path('team/<str:team_code>/members/', TeamApprovedMembersView.as_view(), name='team-members'),
    path('team/<str:team_code>/pending-requests/', TeamPendingRequestsView.as_view(), name='team-pending'),
    path('team/<str:team_code>/rejected-members/', TeamRejectedMembersView.as_view(), name='team-rejected'),

    # Member Actions
    path('approve-member/', ApproveMemberView.as_view(), name='approve-member'),
    path('reject-member/', RejectMemberView.as_view(), name='reject-member'),
    path('approve-rejected-member/', ApproveRejectedMemberView.as_view(), name='approve-rejected-member'),
    path('delete-rejected-member/<uuid:user_id>/', DeleteRejectedMemberView.as_view(), name='delete-rejected-member'),
    path('team/<str:team_code>/member/<uuid:user_id>/', RemoveTeamMemberView.as_view(), name='remove-team-member'),
]
