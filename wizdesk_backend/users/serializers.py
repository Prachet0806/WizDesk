from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User, Team, TeamTransferRequest
from tasks.models import Task, Subtask


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'code', 'name', 'leader', 'created_at']
        read_only_fields = ['id', 'code', 'created_at']


class UserSerializer(serializers.ModelSerializer):
    team = TeamSerializer(read_only=True)
    assigned_tasks = serializers.IntegerField(read_only=True, default=0)
    completed_tasks = serializers.IntegerField(read_only=True, default=0)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'role', 'status', 'team',
            'team_name', 'email_verified', 'approved_by', 
            'approved_at', 'rejected_by', 'rejected_at',
            'assigned_tasks', 'completed_tasks', 'date_joined'
        ]
        read_only_fields = [
            'id', 'status', 'email_verified', 'approved_by',
            'approved_at', 'rejected_by', 'rejected_at'
        ]


class LeaderRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    team_name = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'name', 'team_name']

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_name(self, value):
        import re
        if not value or not re.match(r'^[A-Za-z][A-Za-z\s]*$', value):
            raise serializers.ValidationError("Name must start with a letter and contain only letters and spaces.")
        return value

    def validate_password(self, value):
        if not value:
            raise serializers.ValidationError("Password is required.")
        try:
            validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return value


class MemberRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    team_code = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'name', 'team_code']

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_name(self, value):
        import re
        if not value or not re.match(r'^[A-Za-z][A-Za-z\s]*$', value):
            raise serializers.ValidationError("Name must start with a letter and contain only letters and spaces.")
        return value

    def validate_team_code(self, value):
        from .models import Team
        if not Team.objects.filter(code=value).exists():
            raise serializers.ValidationError("Invalid team code.")
        return value

    def validate_password(self, value):
        if not value:
            raise serializers.ValidationError("Password is required.")
        try:
            validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    team_code = serializers.CharField(required=False)


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    uid = serializers.CharField(required=True)


class CheckMemberStatusSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    team_code = serializers.CharField(required=False)


class TeamTransferRequestSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.name', read_only=True)
    member_email = serializers.CharField(source='member.email', read_only=True)
    current_team_name = serializers.CharField(source='current_team.name', read_only=True)
    future_team_name = serializers.CharField(source='future_team.name', read_only=True)
    future_team_code = serializers.CharField(source='future_team.code', read_only=True)

    class Meta:
        model = TeamTransferRequest
        fields = [
            'id', 'member', 'member_name', 'member_email',
            'current_team', 'current_team_name',
            'future_team', 'future_team_name', 'future_team_code',
            'status', 'current_lead_approved_at', 'future_lead_approved_at',
            'rejected_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'current_lead_approved_at', 
            'future_lead_approved_at', 'rejected_at', 'created_at', 'updated_at'
        ]


class ProcessTransferSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject'])

    def validate_action(self, value):
        if value not in ['approve', 'reject']:
            raise serializers.ValidationError("Action must be 'approve' or 'reject'.")
        return value
