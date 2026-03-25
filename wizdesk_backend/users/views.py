import base64
import random
import string
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from .models import User, Team
from .serializers import UserSerializer

class IsTeamLeader(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.LEADER)

# ---------------------------------------------------------
# AUTH & VERIFICATION VIEWS
# ---------------------------------------------------------

class SendLeaderVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        name = request.data.get('name')
        team_name = request.data.get('teamName')

        if User.objects.filter(email=email).exists():
            return Response({'error': 'User with this email already exists'}, status=status.HTTP_400_BAD_REQUEST)

        # Create unverified user
        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                name=name,
                team_name=team_name,
                role=User.Role.LEADER,
                status=User.Status.APPROVED,
                email_verified=False,
            )
            # Encode token
            token = base64.b64encode(email.encode('utf-8')).decode('utf-8')
            return Response({
                'verificationToken': token,
                'emailSent': True,
                'emailMethod': 'email'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class VerifyLeaderEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'error': 'Token missing'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            email = base64.b64decode(token).decode('utf-8')
            user = User.objects.get(email=email)
            if user.email_verified:
                return Response({'message': 'Already verified'})
            
            user.email_verified = True
            
            # Create team for leader
            team_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            team = Team.objects.create(code=team_code, name=user.team_name, leader=user)
            user.team = team
            user.save()
            return Response({'message': 'Leader registered successfully', 'team_code': team_code}, status=status.HTTP_200_OK)
        except Exception:
            return Response({'error': 'Invalid verification token'}, status=status.HTTP_400_BAD_REQUEST)


class SendMemberVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        name = request.data.get('name')
        team_code = request.data.get('teamCode') or request.data.get('team_code')

        if User.objects.filter(email=email).exists():
            return Response({'error': 'User with this email already exists'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            team = Team.objects.get(code=team_code)
        except Team.DoesNotExist:
            return Response({'error': 'Invalid team code'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                name=name,
                role=User.Role.MEMBER,
                status=User.Status.PENDING,
                team=team,
                email_verified=False
            )
            token = base64.b64encode(email.encode('utf-8')).decode('utf-8')
            return Response({
                'verificationToken': token,
                'teamName': team.name,
                'emailSent': True,
                'emailMethod': 'email'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class VerifyMemberEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'error': 'Token missing'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            email = base64.b64decode(token).decode('utf-8')
            user = User.objects.get(email=email)
            user.email_verified = True
            user.save()
            return Response({
                'teamName': user.team.name if user.team else '',
                'message': 'Email verified successfully. Waiting for leader approval.'
            }, status=status.HTTP_200_OK)
        except Exception:
            return Response({'error': 'Invalid verification token'}, status=status.HTTP_400_BAD_REQUEST)


class CheckMemberStatusView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        team_code = request.data.get('teamCode')
        try:
            user = User.objects.get(email=email)
            
            # Check if team code matches (if provided)
            team_match = True
            if team_code and user.team and user.team.code != team_code:
                team_match = False
                
            can_login = user.status == User.Status.APPROVED and team_match
            
            return Response({
                'status': user.status,
                'role': user.role,
                'canLogin': can_login,
                'teamMatch': team_match,
                'message': 'Team code mismatch' if not team_match else ''
            })
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user = authenticate(username=email, password=password)

        if user:
            if user.role == User.Role.MEMBER and user.status == User.Status.PENDING:
                return Response({'error': 'Your request is pending leader approval.'}, status=status.HTTP_403_FORBIDDEN)
            if user.role == User.Role.MEMBER and user.status == User.Status.REJECTED:
                return Response({'error': 'Your request has been rejected by the leader.'}, status=status.HTTP_403_FORBIDDEN)

            refresh = RefreshToken.for_user(user)
            user_data = UserSerializer(user).data
            if user.team:
                user_data['team_code'] = user.team.code
                user_data['team_name'] = user.team.name
            return Response({
                'token': str(refresh.access_token),
                'refresh': str(refresh),
                'user': user_data,
            })

        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user_data = UserSerializer(request.user).data
        if request.user.team:
            user_data['team_code'] = request.user.team.code
            user_data['team_name'] = request.user.team.name
        return Response(user_data)


# ---------------------------------------------------------
# TEAM LIST VIEWS
# ---------------------------------------------------------

class TeamAllMembersView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.filter(team__code=team_code, status=User.Status.APPROVED)
        return Response(UserSerializer(qs, many=True).data)

class TeamApprovedMembersView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.filter(team__code=team_code, status=User.Status.APPROVED, role=User.Role.MEMBER)
        return Response(UserSerializer(qs, many=True).data)

class TeamPendingRequestsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.filter(team__code=team_code, status=User.Status.PENDING)
        return Response(UserSerializer(qs, many=True).data)

class TeamRejectedMembersView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.filter(team__code=team_code, status=User.Status.REJECTED)
        return Response(UserSerializer(qs, many=True).data)


# ---------------------------------------------------------
# MEMBER ACTIONS VIEWS
# ---------------------------------------------------------

class ApproveMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    def post(self, request):
        user_id = request.data.get('userId')
        try:
            member = User.objects.get(id=user_id, team=request.user.team)
            member.status = User.Status.APPROVED
            member.approved_by = request.user
            member.approved_at = timezone.now()
            member.save()
            return Response({'message': 'Member approved successfully'})
        except User.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

class RejectMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    def post(self, request):
        user_id = request.data.get('userId')
        try:
            member = User.objects.get(id=user_id, team=request.user.team)
            member.status = User.Status.REJECTED
            member.rejected_by = request.user
            member.rejected_at = timezone.now()
            member.save()
            return Response({
                'message': 'Member rejected successfully',
                'user': UserSerializer(member).data
            })
        except User.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

class ApproveRejectedMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    def post(self, request):
        return ApproveMemberView().post(request)

class DeleteRejectedMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    def delete(self, request, user_id):
        try:
            member = User.objects.get(id=user_id, team=request.user.team, status=User.Status.REJECTED)
            member.delete()
            return Response({'message': 'Rejected member deleted'})
        except User.DoesNotExist:
            return Response({'error': 'Rejected member not found'}, status=status.HTTP_404_NOT_FOUND)

class RemoveTeamMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    def delete(self, request, team_code, user_id):
        if request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        try:
            member = User.objects.get(id=user_id, team=request.user.team, role=User.Role.MEMBER)
            member.delete() # Hard delete for simplicity, or we could just set team=None
            return Response({'message': 'Member removed dynamically'})
        except User.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)
