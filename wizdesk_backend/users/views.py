import logging
import secrets
import string
import unicodedata
from django.conf import settings
from django.db import connection, transaction, IntegrityError
from django.contrib.auth import authenticate
from django.core import signing
from django.core.mail import send_mail
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.utils import timezone
from django.db.models import Count, Q
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response
from .api import ObjectAPIView as APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenRefreshView
from .models import User, Team, TeamTransferRequest
from .serializers import UserSerializer, TeamTransferRequestSerializer
from .permissions import IsTeamLeader, IsApprovedTeamMember, eligible
from .authentication import EligibleTokenRefreshSerializer
from tasks.services import release_unfinished, Conflict

logger = logging.getLogger(__name__)
TOKEN_SALT = 'wizdesk.email-verification.v1'


def password_fingerprint(user):
    from django.utils.crypto import salted_hmac
    return salted_hmac(TOKEN_SALT, user.password).hexdigest()


def verification_token(user):
    return signing.dumps({'uid': str(user.pk), 'role': user.role, 'email': user.email,
                          'password': password_fingerprint(user)}, salt=TOKEN_SALT, compress=True)


def _send_verification_email(user, token=None, uid=None, kind='leader'):
    # Tokens never appear in responses or application error logs.
    token = token or verification_token(user)
    uid = uid or urlsafe_base64_encode(force_bytes(user.pk))
    path = 'register-leader.html' if user.role == User.Role.LEADER else 'member-register.html'
    frontend = settings.FRONTEND_URL or ('https://' + settings.RENDER_EXTERNAL_HOSTNAME if getattr(settings, 'RENDER_EXTERNAL_HOSTNAME', '') else '')
    if not frontend:
        logger.error('FRONTEND_URL is required for email delivery')
        return False
    link = f'{frontend}/{path}?uid={uid}&token={token}'
    try:
        send_mail('Verify your WizDesk email', f'Hi {user.name},\n\nVerify your email: {link}\n\nThis link expires in 24 hours.', settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        return True
    except Exception:
        logger.error('Verification delivery failed', exc_info=False)
        return False


def create_team(user):
    for attempt in range(5):
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        try:
            with transaction.atomic():
                return Team.objects.create(code=code, name=user.team_name or f"{user.name}'s Team", leader=user)
        except IntegrityError:
            if not Team.objects.filter(code=code).exists():
                raise
    raise Conflict('Could not allocate a team code. Retry registration.')


class RegistrationInput(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    name = serializers.CharField(max_length=255)
    team_name = serializers.CharField(max_length=255, required=False)
    team_code = serializers.CharField(max_length=20, required=False)

    def validate_name(self, value):
        if not any(c.isalpha() for c in value) or any(not(c.isalpha() or unicodedata.category(c).startswith('M') or c.isspace() or c in "'-.") for c in value):
            raise serializers.ValidationError('Enter a valid name.')
        return value

    def validate(self, values):
        from django.contrib.auth.password_validation import validate_password
        values['email'] = values['email'].lower()
        candidate = User(email=values['email'], username=values['email'], name=values['name'])
        try:
            validate_password(values['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages})
        return values


class PublicView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]


class HealthCheckView(PublicView):
    throttle_classes = []

    def get(self, request):
        db_status = 'ok'
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
        except Exception:
            db_status = 'error'
        return Response({'status': 'healthy' if db_status == 'ok' else 'unhealthy',
                         'database': db_status, 'version': settings.APP_VERSION}, status=200 if db_status == 'ok' else 503)


class LivenessView(PublicView):
    throttle_classes = []

    def get(self, request):
        return Response({'status': 'alive', 'version': settings.APP_VERSION})


class AuthConfigView(PublicView):
    def get(self, request):
        return Response({'verificationRequired': settings.EMAIL_VERIFICATION_REQUIRED, 'minimumPasswordLength': 8})


class RegistrationView(PublicView):
    throttle_scope = 'registration'
    role = User.Role.MEMBER

    def post(self, request):
        payload = dict(request.data)
        payload['team_name'] = payload.get('team_name') or payload.get('teamName')
        payload['team_code'] = payload.get('team_code') or payload.get('teamCode')
        payload = {k: v for k, v in payload.items() if v is not None}
        validator = RegistrationInput(data=payload)
        validator.is_valid(raise_exception=True)
        data = validator.validated_data
        if self.role == User.Role.LEADER and not data.get('team_name'):
            raise ValidationError({'team_name': 'Team name is required.'})
        team = None
        if self.role == User.Role.MEMBER:
            team = Team.objects.filter(code=data.get('team_code', '').upper()).first()
            if not team or not team.leader_id:
                raise ValidationError({'team_code': 'Invalid team code.'})
        generic = {'message': 'If eligible, a verification email will arrive. You can request another below.',
                   'deliveryStatus': 'accepted', 'emailMethod': 'email', 'emailSent': None}
        try:
            with transaction.atomic():
                if User.objects.filter(email__iexact=data['email']).exists():
                    if settings.EMAIL_VERIFICATION_REQUIRED:
                        return Response(generic, status=202)
                    raise ValidationError('Registration unavailable. Try signing in.')
                user = User.objects.create_user(username=secrets.token_hex(16), email=data['email'], password=data['password'],
                    name=data['name'], team_name=data.get('team_name'), role=self.role, team=team,
                    status=User.Status.APPROVED if self.role == User.Role.LEADER else User.Status.PENDING,
                    email_verified=not settings.EMAIL_VERIFICATION_REQUIRED)
                if settings.EMAIL_VERIFICATION_REQUIRED:
                    transaction.on_commit(lambda: _send_verification_email(user))
                    return Response(generic, status=202)
                if self.role == User.Role.LEADER:
                    user.team = create_team(user)
                    user.save(update_fields=['team'])
                return Response({'message': 'Registration complete.', 'verificationSkipped': True,
                                 'teamCode': user.team.code, 'teamName': user.team.name,
                                 'emailSent': False, 'emailMethod': 'none', 'user': UserSerializer(user).data}, status=201)
        except IntegrityError:
            if User.objects.filter(email__iexact=data['email']).exists():
                if settings.EMAIL_VERIFICATION_REQUIRED:
                    return Response(generic, status=202)
                raise ValidationError('Registration unavailable. Try signing in.')
            raise


class SendLeaderVerificationView(RegistrationView):
    role = User.Role.LEADER


class SendMemberVerificationView(RegistrationView):
    role = User.Role.MEMBER


class VerifyEmailView(PublicView):
    throttle_scope = 'auth'
    role = User.Role.MEMBER

    @transaction.atomic
    def post(self, request):
        token = serializers.CharField(max_length=4096).run_validation(request.data.get('token'))
        encoded_uid = serializers.CharField(max_length=128).run_validation(request.data.get('uid'))
        try:
            data = signing.loads(token, salt=TOKEN_SALT, max_age=86400)
            uid = force_str(urlsafe_base64_decode(encoded_uid))
            user = User.objects.select_for_update().get(pk=uid, role=self.role)
            if data != {'uid': str(user.pk), 'role': user.role, 'email': user.email, 'password': password_fingerprint(user)}:
                raise ValueError('Wrong account or purpose')
        except (signing.BadSignature, User.DoesNotExist, DjangoValidationError, ValueError, TypeError, OverflowError, UnicodeError):
            raise ValidationError('Invalid or expired verification link.')
        user.email_verified = True
        if self.role == User.Role.LEADER and not user.team_id:
            user.team = create_team(user)
        user.save(update_fields=['email_verified', 'team'])
        return Response({'message': 'Email verified.', 'teamCode': user.team.code if user.team else '',
                         'teamName': user.team.name if user.team else '', 'user': UserSerializer(user).data})


class VerifyLeaderEmailView(VerifyEmailView):
    role = User.Role.LEADER


class VerifyMemberEmailView(VerifyEmailView):
    role = User.Role.MEMBER


class ResendVerificationView(PublicView):
    throttle_scope = 'registration'

    def post(self, request):
        field = serializers.EmailField()
        email = field.run_validation(request.data.get('email'))
        user = User.objects.filter(email__iexact=email, email_verified=False, is_active=True).first()
        if user and settings.EMAIL_VERIFICATION_REQUIRED:
            _send_verification_email(user)
        return Response({'message': 'If eligible, a verification email will arrive.', 'deliveryStatus': 'accepted'}, status=202)


class CheckMemberStatusView(PublicView):
    throttle_scope = 'auth'

    def post(self, request):
        return Response({'message': 'Sign in to check your membership status.'})


class LoginView(PublicView):
    throttle_scope = 'auth'

    def post(self, request):
        email = serializers.EmailField().run_validation(request.data.get('email'))
        password = serializers.CharField(trim_whitespace=False).run_validation(request.data.get('password'))
        candidates = User.objects.filter(email__iexact=email)
        candidate = candidates.first() if candidates.count() == 1 else None
        if candidate:
            user = authenticate(request, username=candidate.email, password=password)
        else:
            # Match the password-hash work performed for an incorrect password.
            User().set_password(password)
            user = None
        if not user:
            return Response({'error': 'Invalid credentials'}, status=401)
        if settings.EMAIL_VERIFICATION_REQUIRED and not user.email_verified:
            return Response({'error': 'Verify your email before signing in.'}, status=403)
        if not eligible(user):
            return Response({'error': 'An approved team membership is required.'}, status=403)
        team_code = request.data.get('teamCode') or request.data.get('team_code')
        if team_code and team_code != user.team.code:
            return Response({'error': 'Invalid team code for this account.'}, status=401)
        refresh = RefreshToken.for_user(user)
        data = UserSerializer(user).data
        data.update(team_code=user.team.code, team_name=user.team.name)
        return Response({'token': str(refresh.access_token), 'refresh': str(refresh), 'user': data})


class EligibleTokenRefreshView(TokenRefreshView):
    serializer_class = EligibleTokenRefreshSerializer
    authentication_classes = []
    throttle_scope = 'auth'


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = 'auth'

    def post(self, request):
        try:
            RefreshToken(request.data.get('refresh', '')).blacklist()
        except (TokenError, TypeError):
            pass  # Idempotent logout, including expired tokens.
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsApprovedTeamMember]

    def get(self, request):
        user_data = UserSerializer(request.user).data
        if request.user.team:
            user_data['team_code'] = request.user.team.code
            user_data['team_name'] = request.user.team.name
        return Response(user_data)


def paginated(request, queryset, serializer_class):
    from rest_framework.pagination import PageNumberPagination
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(serializer_class(page, many=True).data)


def cancel_transfers(member, actor):
    TeamTransferRequest.objects.filter(member=member, status__in=[
        TeamTransferRequest.Status.PENDING_CURRENT, TeamTransferRequest.Status.PENDING_FUTURE
    ]).update(status=TeamTransferRequest.Status.REJECTED, rejected_by=actor,
              rejected_at=timezone.now(), updated_at=timezone.now())


# ---------------------------------------------------------
# TEAM LIST VIEWS
# ---------------------------------------------------------

class TeamAllMembersView(APIView):
    permission_classes = [IsApprovedTeamMember]
    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.select_related('team').filter(team__code=team_code, status=User.Status.APPROVED).annotate(
            assigned_tasks=Count('assigned_subtasks', filter=Q(assigned_subtasks__task__team=request.user.team)),
            completed_tasks=Count('assigned_subtasks', filter=Q(assigned_subtasks__task__team=request.user.team, assigned_subtasks__progress='completed'))
        )
        return paginated(request, qs.order_by("date_joined", "pk"), UserSerializer)

class TeamApprovedMembersView(APIView):
    permission_classes = [IsApprovedTeamMember]
    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.select_related('team').filter(team__code=team_code, status=User.Status.APPROVED, role=User.Role.MEMBER).annotate(
            assigned_tasks=Count('assigned_subtasks', filter=Q(assigned_subtasks__task__team=request.user.team)),
            completed_tasks=Count('assigned_subtasks', filter=Q(assigned_subtasks__task__team=request.user.team, assigned_subtasks__progress='completed'))
        )
        return paginated(request, qs.order_by("date_joined", "pk"), UserSerializer)

class TeamPendingRequestsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.select_related('team').filter(team__code=team_code, status=User.Status.PENDING)
        return paginated(request, qs.order_by("date_joined", "pk"), UserSerializer)

class TeamRejectedMembersView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    def get(self, request, team_code):
        if not request.user.team or request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.select_related('team').filter(team__code=team_code, status=User.Status.REJECTED)
        return paginated(request, qs.order_by("date_joined", "pk"), UserSerializer)


# ---------------------------------------------------------
# MEMBER ACTIONS VIEWS
# ---------------------------------------------------------

class ApproveMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    throttle_scope = 'mutation'

    @transaction.atomic
    def post(self, request):
        user_id = request.data.get('userId')
        try:
            member = User.objects.select_for_update().get(id=user_id, team=request.user.team, role=User.Role.MEMBER)
            member.status = User.Status.APPROVED
            member.approved_by = request.user
            member.approved_at = timezone.now()
            member.save()
            return Response({'message': 'Member approved successfully'})
        except (User.DoesNotExist, DjangoValidationError):
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

class RejectMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    throttle_scope = 'mutation'

    @transaction.atomic
    def post(self, request):
        user_id = request.data.get('userId')
        try:
            member = User.objects.select_for_update().get(id=user_id, team=request.user.team, role=User.Role.MEMBER)
            cancel_transfers(member, request.user)
            release_unfinished(member, request.user.team)
            member.status = User.Status.REJECTED
            member.rejected_by = request.user
            member.rejected_at = timezone.now()
            member.save()
            return Response({
                'message': 'Member rejected successfully',
                'user': UserSerializer(member).data
            })
        except (User.DoesNotExist, DjangoValidationError):
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

class ApproveRejectedMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    throttle_scope = 'mutation'

    def post(self, request):
        return ApproveMemberView().post(request)

class DeleteRejectedMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    throttle_scope = 'mutation'

    @transaction.atomic
    def delete(self, request, user_id):
        try:
            member = User.objects.select_for_update().get(id=user_id, team=request.user.team, role=User.Role.MEMBER, status=User.Status.REJECTED)
            cancel_transfers(member, request.user)
            release_unfinished(member, request.user.team)
            member.team = None
            member.save(update_fields=['team'])
            return Response({'message': 'Rejected membership removed'})
        except (User.DoesNotExist, DjangoValidationError):
            return Response({'error': 'Rejected member not found'}, status=status.HTTP_404_NOT_FOUND)

class RemoveTeamMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeamLeader]
    throttle_scope = 'mutation'

    @transaction.atomic
    def delete(self, request, team_code, user_id):
        if request.user.team.code != team_code:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        try:
            member = User.objects.select_for_update().get(id=user_id, team=request.user.team, role=User.Role.MEMBER)
            cancel_transfers(member, request.user)
            release_unfinished(member, request.user.team)
            member.team = None
            member.status = User.Status.REJECTED
            member.save(update_fields=['team', 'status'])
            return Response({'message': 'Member removed dynamically'})
        except (User.DoesNotExist, DjangoValidationError):
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------
# TEAM TRANSFER VIEWS
# ---------------------------------------------------------

class RequestTransferView(APIView):
    permission_classes = [IsApprovedTeamMember]
    throttle_scope = 'mutation'

    @transaction.atomic
    def post(self, request):
        member = User.objects.select_for_update().get(pk=request.user.pk)
        if not eligible(member):
            raise PermissionDenied('Membership changed.')
        future_team_code = request.data.get('future_team_code')
        try:
            future_team = Team.objects.get(code=future_team_code)
        except Team.DoesNotExist:
            return Response({'error': 'Invalid future team code'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.role != User.Role.MEMBER:
            return Response({'error': 'Only team members can request a transfer.'}, status=status.HTTP_403_FORBIDDEN)

        if member.status != User.Status.APPROVED:
            return Response({'error': 'Your account must be approved before requesting a transfer.'}, status=status.HTTP_403_FORBIDDEN)

        if not future_team.leader:
            return Response({'error': 'The target team has no leader yet. Please try again later.'}, status=status.HTTP_400_BAD_REQUEST)

        if not member.team:
             return Response({'error': 'You must be in a team to request a transfer.'}, status=status.HTTP_400_BAD_REQUEST)

        if member.team == future_team:
            return Response({'error': 'You are already in this team.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if there's already a pending request
        if TeamTransferRequest.objects.filter(member=member, status__in=[TeamTransferRequest.Status.PENDING_CURRENT, TeamTransferRequest.Status.PENDING_FUTURE]).exists():
             return Response({'error': 'You already have a pending transfer request.'}, status=status.HTTP_400_BAD_REQUEST)

        transfer_request = TeamTransferRequest.objects.create(
            member=member,
            current_team=member.team,
            future_team=future_team,
            status=TeamTransferRequest.Status.PENDING_CURRENT
        )
        return Response(TeamTransferRequestSerializer(transfer_request).data, status=status.HTTP_201_CREATED)

class PendingTransfersView(APIView):
    permission_classes = [IsApprovedTeamMember]

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

        return paginated(request, qs.select_related('member', 'current_team', 'future_team').order_by('-created_at', '-pk'), TeamTransferRequestSerializer)

class ProcessTransferView(APIView):
    permission_classes = [IsTeamLeader]
    throttle_scope = 'mutation'

    @transaction.atomic
    def post(self, request, pk):
        action = request.data.get('action')
        if action not in ('approve', 'reject'):
            raise ValidationError({'action': 'Choose approve or reject.'})
        snapshot = TeamTransferRequest.objects.filter(pk=pk).first()
        if not snapshot:
            return Response({'error': 'Transfer request not found'}, status=404)
        member = User.objects.select_for_update().get(pk=snapshot.member_id)
        transfer = TeamTransferRequest.objects.select_for_update(of=('self',)).select_related('current_team', 'future_team').get(pk=pk)
        expected_team = transfer.current_team if transfer.status == TeamTransferRequest.Status.PENDING_CURRENT else transfer.future_team
        if transfer.status not in (TeamTransferRequest.Status.PENDING_CURRENT, TeamTransferRequest.Status.PENDING_FUTURE):
            raise Conflict('This transfer is no longer pending.')
        if expected_team.leader_id != request.user.pk:
            raise PermissionDenied('You are not the leader for this approval stage.')
        if member.team_id != transfer.current_team_id or member.status != User.Status.APPROVED:
            raise Conflict('Membership changed. This transfer cannot proceed.')
        if action == 'reject':
            transfer.status = TeamTransferRequest.Status.REJECTED
            transfer.rejected_by = request.user
            transfer.rejected_at = timezone.now()
        elif transfer.status == TeamTransferRequest.Status.PENDING_CURRENT:
            transfer.status = TeamTransferRequest.Status.PENDING_FUTURE
            transfer.current_lead_approved_at = timezone.now()
        else:
            release_unfinished(member, transfer.current_team)
            member.team = transfer.future_team
            member.save(update_fields=['team'])
            transfer.status = TeamTransferRequest.Status.APPROVED
            transfer.future_lead_approved_at = timezone.now()
        transfer.save()
        return Response({'message': 'Transfer updated.', 'status': transfer.status})
