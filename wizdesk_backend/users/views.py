import random
import string
import re
import logging
from django.conf import settings
from django.db import connection, transaction
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db.models import Count, Q
from .models import User, Team, TeamTransferRequest
from .serializers import UserSerializer, TeamTransferRequestSerializer


logger = logging.getLogger(__name__)


def _send_verification_email(user, token, uid, kind="leader"):
    """Send the email-verification link. Never raises — logs on failure.

    Tokens are delivered via email only, never in API responses, so a
    leaked response cannot be used to verify an address the attacker
    does not control.
    """
    frontend = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    if frontend:
        verify_path = 'register-leader.html' if kind == "leader" else 'member-register.html'
        link = f"{frontend}/{verify_path}?uid={uid}&token={token}"
    else:
        link = f"(no FRONTEND_URL configured) uid={uid} token={token}"
    subject = "Verify your WizDesk email"
    message = (
        f"Hi {user.name or user.email},\n\n"
        f"Please verify your email address by opening this link:\n{link}\n\n"
        f"This link expires. If you did not register, ignore this email."
    )
    try:
        send_mail(subject, message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [user.email], fail_silently=False)
        logger.info("Verification email queued for %s", user.email)
        return True
    except Exception:
        # Console backend or missing SMTP in dev still surfaces the link in logs.
        logger.exception("Failed to send verification email to %s; link: %s", user.email, link)
        return False


class HealthCheckView(APIView):
    """
    Health check endpoint for uptime monitoring (UptimeRobot, Render, etc.)
    Returns 200 if healthy, 503 if database unavailable.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # Check database connectivity
        db_status = "ok"
        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            db_status = "error"

        status_code = 200 if db_status == "ok" else 503
        return Response({
            "status": "healthy" if db_status == "ok" else "unhealthy",
            "database": db_status,
            "version": getattr(settings, 'APP_VERSION', '1.0.0'),
        }, status=status_code)


class IsTeamLeader(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.LEADER)

# ---------------------------------------------------------
# AUTH & VERIFICATION VIEWS
# ---------------------------------------------------------

class SendLeaderVerificationView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'registration'

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        name = request.data.get('name')
        team_name = request.data.get('teamName')

        # Validate input (but don't reveal if email exists)
        if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            return Response({'error': 'Invalid email address'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not name or not re.match(r'^[A-Za-z][A-Za-z\s]*$', name):
            return Response({'error': 'Name must start with a letter and contain only letters and spaces'}, status=status.HTTP_400_BAD_REQUEST)

        if not password:
            return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password)
        except ValidationError as exc:
            return Response(
                {'error': exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Always return generic success to prevent email enumeration
        # Actual user creation happens in try block; if email exists, IntegrityError is caught
        generic_response = {
            'message': 'If this email is not registered, a verification email has been sent.',
            'emailSent': True,
            'emailMethod': 'email'
        }

        try:
            verification_required = getattr(settings, 'EMAIL_VERIFICATION_REQUIRED', False)
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                name=name,
                team_name=team_name,
                role=User.Role.LEADER,
                status=User.Status.APPROVED,
                email_verified=not verification_required,
            )
            if not verification_required:
                team_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                team = Team.objects.create(code=team_code, name=user.team_name or f"{name}'s Team", leader=user)
                user.team = team
                user.save()
                generic_response.update({
                    'message': 'Leader registered successfully',
                    'teamCode': team_code,
                    'verificationToken': '',
                    'emailSent': False,
                    'emailMethod': 'none',
                    'verificationSkipped': True,
                    'user': UserSerializer(user).data,
                })
                return Response(generic_response, status=status.HTTP_201_CREATED)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            # Deliver token via email only — never in the API response.
            _send_verification_email(user, token, uid, kind="leader")
            return Response(generic_response, status=status.HTTP_200_OK)
        except Exception as e:
            # If email already exists (IntegrityError), still return generic success
            logger.info(f"Registration attempt for existing email: {email}")
            return Response(generic_response, status=status.HTTP_200_OK)


class VerifyLeaderEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        token = request.data.get('token')
        uid = request.data.get('uid')
        if not token or not uid:
            return Response({'error': 'Token and UID required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response({'error': 'Invalid verification link'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not default_token_generator.check_token(user, token):
            return Response({'error': 'Invalid or expired verification token'}, status=status.HTTP_400_BAD_REQUEST)

        if user.email_verified and user.team:
            # Verification ON HOLD / idempotent: already done
            return Response({
                'message': 'Leader registered successfully',
                'teamCode': user.team.code,
                'emailSent': False,
                'emailMethod': 'none',
                'verificationSkipped': True,
                'user': UserSerializer(user).data,
            })
        
        user.email_verified = True
        
        # Create team for leader
        team_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        team = Team.objects.create(code=team_code, name=user.team_name, leader=user)
        user.team = team
        user.save()
        return Response({
            'message': 'Leader registered successfully', 
            'teamCode': team_code,
            'emailSent': True,
            'emailMethod': 'manual',
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


class SendMemberVerificationView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'registration'

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        name = request.data.get('name')
        team_code = request.data.get('teamCode') or request.data.get('team_code')

        # Validation (but don't reveal if email exists)
        if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            return Response({'error': 'Invalid email address'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not name or not re.match(r'^[A-Za-z][A-Za-z\s]*$', name):
            return Response({'error': 'Name must start with a letter and contain only letters and spaces'}, status=status.HTTP_400_BAD_REQUEST)

        if not password:
            return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password)
        except ValidationError as exc:
            return Response(
                {'error': exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            team = Team.objects.get(code=team_code)
        except Team.DoesNotExist:
            return Response({'error': 'Invalid team code'}, status=status.HTTP_400_BAD_REQUEST)

        # Always return generic success to prevent email enumeration
        generic_response = {
            'message': 'If this email is not registered, a verification email has been sent.',
            'teamName': team.name,
            'emailSent': True,
            'emailMethod': 'email'
        }

        try:
            verification_required = getattr(settings, 'EMAIL_VERIFICATION_REQUIRED', False)
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                name=name,
                role=User.Role.MEMBER,
                status=User.Status.PENDING,
                team=team,
                email_verified=not verification_required
            )
            if not verification_required:
                generic_response.update({
                    'message': 'Registration received. Waiting for leader approval.',
                    'verificationToken': '',
                    'verificationUid': '',
                    'emailSent': False,
                    'emailMethod': 'none',
                    'verificationSkipped': True,
                })
                return Response(generic_response, status=status.HTTP_201_CREATED)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            # Deliver token via email only — never in the API response.
            _send_verification_email(user, token, uid, kind="member")
            return Response(generic_response, status=status.HTTP_200_OK)
        except Exception as e:
            # If email already exists (IntegrityError), still return generic success
            logger.info(f"Member registration attempt for existing email: {email}")
            return Response(generic_response, status=status.HTTP_200_OK)


class VerifyMemberEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        token = request.data.get('token')
        uid = request.data.get('uid')
        if not token or not uid:
            return Response({'error': 'Token and UID required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response({'error': 'Invalid verification link'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not default_token_generator.check_token(user, token):
            return Response({'error': 'Invalid or expired verification token'}, status=status.HTTP_400_BAD_REQUEST)

        if not getattr(settings, 'EMAIL_VERIFICATION_REQUIRED', False):
            # Verification ON HOLD: idempotent success
            user.email_verified = True
            user.save(update_fields=['email_verified'])
            return Response({
                'teamName': user.team.name if user.team else '',
                'message': 'Registration received. Waiting for leader approval.',
                'verificationSkipped': True,
            })
        user.email_verified = True
        user.save()
        return Response({
            'teamName': user.team.name if user.team else '',
            'message': 'Email verified successfully. Waiting for leader approval.'
        }, status=status.HTTP_200_OK)


class CheckMemberStatusView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        email = request.data.get('email')
        team_code = request.data.get('teamCode')
        user = User.objects.filter(email=email).first()
        
        if not user:
            # Return generic response to prevent email enumeration
            return Response({
                'status': 'not_found',
                'role': None,
                'canLogin': False,
                'teamMatch': False,
                'message': 'If this email is registered, status information has been sent.'
            })
        
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


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        team_code = request.data.get('teamCode')
        
        user = authenticate(username=email, password=password)
        
        if user:
            # Verify team code if provided
            if team_code and user.team and user.team.code != team_code:
                return Response({'error': 'Invalid team code for this account.'}, status=status.HTTP_401_UNAUTHORIZED)

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
        qs = User.objects.filter(team__code=team_code, status=User.Status.APPROVED).annotate(
            assigned_tasks=Count('assigned_subtasks'),
            completed_tasks=Count('assigned_subtasks', filter=Q(assigned_subtasks__status='completed'))
        )
        return Response(UserSerializer(qs, many=True).data)

class TeamApprovedMembersView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.filter(team__code=team_code, status=User.Status.APPROVED, role=User.Role.MEMBER).annotate(
            assigned_tasks=Count('assigned_subtasks'),
            completed_tasks=Count('assigned_subtasks', filter=Q(assigned_subtasks__status='completed'))
        )
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
    throttle_scope = 'mutation'

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
    throttle_scope = 'mutation'

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
    throttle_scope = 'mutation'

    def post(self, request):
        return ApproveMemberView().post(request)

class DeleteRejectedMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    throttle_scope = 'mutation'

    def delete(self, request, user_id):
        try:
            member = User.objects.get(id=user_id, team=request.user.team, status=User.Status.REJECTED)
            member.delete()
            return Response({'message': 'Rejected member deleted'})
        except User.DoesNotExist:
            return Response({'error': 'Rejected member not found'}, status=status.HTTP_404_NOT_FOUND)

class RemoveTeamMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    throttle_scope = 'mutation'

    def delete(self, request, team_code, user_id):
        if request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        try:
            member = User.objects.get(id=user_id, team=request.user.team, role=User.Role.MEMBER)
            member.delete() # Hard delete for simplicity, or we could just set team=None
            return Response({'message': 'Member removed dynamically'})
        except User.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------
# TEAM TRANSFER VIEWS
# ---------------------------------------------------------

class RequestTransferView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'mutation'

    def post(self, request):
        future_team_code = request.data.get('future_team_code')
        try:
            future_team = Team.objects.get(code=future_team_code)
        except Team.DoesNotExist:
            return Response({'error': 'Invalid future team code'}, status=status.HTTP_400_BAD_REQUEST)
        
        if request.user.role != User.Role.MEMBER:
            return Response({'error': 'Only team members can request a transfer.'}, status=status.HTTP_403_FORBIDDEN)

        if request.user.status != User.Status.APPROVED:
            return Response({'error': 'Your account must be approved before requesting a transfer.'}, status=status.HTTP_403_FORBIDDEN)

        if not future_team.leader:
            return Response({'error': 'The target team has no leader yet. Please try again later.'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.team:
             return Response({'error': 'You must be in a team to request a transfer.'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.team == future_team:
            return Response({'error': 'You are already in this team.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if there's already a pending request
        if TeamTransferRequest.objects.filter(member=request.user, status__in=[TeamTransferRequest.Status.PENDING_CURRENT, TeamTransferRequest.Status.PENDING_FUTURE]).exists():
             return Response({'error': 'You already have a pending transfer request.'}, status=status.HTTP_400_BAD_REQUEST)

        transfer_request = TeamTransferRequest.objects.create(
            member=request.user,
            current_team=request.user.team,
            future_team=future_team,
            status=TeamTransferRequest.Status.PENDING_CURRENT
        )
        return Response(TeamTransferRequestSerializer(transfer_request).data, status=status.HTTP_201_CREATED)

class PendingTransfersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == User.Role.MEMBER:
            qs = TeamTransferRequest.objects.filter(member=user).order_by('-created_at')
        else:
            # For leader, show outgoing (current lead) and incoming (future lead)
            qs = TeamTransferRequest.objects.filter(
                Q(current_team__leader=user, status=TeamTransferRequest.Status.PENDING_CURRENT) |
                Q(future_team__leader=user, status=TeamTransferRequest.Status.PENDING_FUTURE)
            ).order_by('-created_at')
        
        return Response(TeamTransferRequestSerializer(qs, many=True).data)

class ProcessTransferView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    throttle_scope = 'mutation'

    def post(self, request, pk):
        action = request.data.get('action') # 'approve' or 'reject'
        try:
            transfer = TeamTransferRequest.objects.get(pk=pk)
        except TeamTransferRequest.DoesNotExist:
            return Response({'error': 'Transfer request not found'}, status=status.HTTP_404_NOT_FOUND)

        if action == 'reject':
            if transfer.status == TeamTransferRequest.Status.PENDING_CURRENT:
                if transfer.current_team.leader != request.user:
                    return Response({'error': 'You are not the leader of the current team.'}, status=status.HTTP_403_FORBIDDEN)
            elif transfer.status == TeamTransferRequest.Status.PENDING_FUTURE:
                if transfer.future_team.leader != request.user:
                    return Response({'error': 'You are not the leader of the future team.'}, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({'error': 'This transfer request is no longer pending.'}, status=status.HTTP_400_BAD_REQUEST)

            transfer.status = TeamTransferRequest.Status.REJECTED
            transfer.rejected_by = request.user
            transfer.rejected_at = timezone.now()
            transfer.save()
            return Response({'message': 'Transfer rejected'})

        if action == 'approve':
            if transfer.status == TeamTransferRequest.Status.PENDING_CURRENT:
                if transfer.current_team.leader != request.user:
                    return Response({'error': 'You are not the leader of the current team.'}, status=status.HTTP_403_FORBIDDEN)
                
                with transaction.atomic():
                    # Lock the transfer row to prevent race conditions
                    transfer = TeamTransferRequest.objects.select_for_update().get(pk=pk)
                    if transfer.status != TeamTransferRequest.Status.PENDING_CURRENT:
                        return Response({'error': 'This transfer request is no longer pending.'}, status=status.HTTP_400_BAD_REQUEST)
                    
                    transfer.status = TeamTransferRequest.Status.PENDING_FUTURE
                    transfer.current_lead_approved_at = timezone.now()
                    transfer.save()
                return Response({'message': 'Approved by current lead. Waiting for future lead approval.'})

            elif transfer.status == TeamTransferRequest.Status.PENDING_FUTURE:
                if transfer.future_team.leader != request.user:
                    return Response({'error': 'You are not the leader of the future team.'}, status=status.HTTP_403_FORBIDDEN)
                
                with transaction.atomic():
                    # Lock the transfer row and related objects to prevent race conditions
                    transfer = TeamTransferRequest.objects.select_for_update().get(pk=pk)
                    if transfer.status != TeamTransferRequest.Status.PENDING_FUTURE:
                        return Response({'error': 'This transfer request is no longer pending.'}, status=status.HTTP_400_BAD_REQUEST)
                    
                    transfer.status = TeamTransferRequest.Status.APPROVED
                    transfer.future_lead_approved_at = timezone.now()
                    transfer.save()
                    
                    # Perform the move
                    member = transfer.member
                    member.team = transfer.future_team
                    # Unassign from current tasks
                    from tasks.models import Subtask
                    Subtask.objects.filter(assigned_to=member, status__in=[Subtask.Status.ASSIGNED, Subtask.Status.TAKEN]).update(assigned_to=None, status=Subtask.Status.AVAILABLE, progress='not_started')
                    member.save()
                
                return Response({'message': 'Transfer approved successfully. Member has been moved.'})

        return Response({'error': 'Invalid action or state'}, status=status.HTTP_400_BAD_REQUEST)
