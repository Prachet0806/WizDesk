from rest_framework import serializers
from .models import User, Team, TeamTransferRequest

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

class MemberRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    team_code = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'name', 'team_code']

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
