from django.db import transaction
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework.authentication import CSRFCheck

from .permissions import eligible


class EligibleJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        raw = request.COOKIES.get("wizdesk_access")
        if not raw:
            return super().authenticate(request)
        self.enforce_csrf(request)
        validated = self.get_validated_token(raw)
        return self.get_user(validated), validated

    def enforce_csrf(self, request):
        check = CSRFCheck(lambda req: None)
        django_request = getattr(request, "_request", request)
        check.process_request(django_request)
        reason = check.process_view(django_request, lambda req: None, (), {})
        if reason:
            raise AuthenticationFailed(f"CSRF Failed: {reason}")

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not eligible(user):
            raise AuthenticationFailed("Account is not eligible for team access.")
        return user


class EligibleTokenRefreshSerializer(TokenRefreshSerializer):
    @transaction.atomic
    def validate(self, attrs):
        token = RefreshToken(attrs["refresh"])
        from .models import User

        # Serialize rotations with each other and membership changes.
        user = User.objects.select_for_update().filter(pk=token["user_id"]).first()
        if not eligible(user):
            raise AuthenticationFailed("Account is not eligible for team access.")
        if (
            api_settings.CHECK_REVOKE_TOKEN
            and token.get(api_settings.REVOKE_TOKEN_CLAIM)
            != get_md5_hash_password(user.password)
        ):
            raise AuthenticationFailed("Password changed. Sign in again.")
        return super().validate(attrs)
