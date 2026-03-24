from rest_framework import serializers
from .models import User, Team

class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'code', 'name', 'leader', 'created_at']
        read_only_fields = ['id', 'code', 'created_at']

class UserSerializer(serializers.ModelSerializer):
    team = TeamSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'role', 'status', 'team',
            'team_name', 'email_verified', 'approved_by', 
            'approved_at', 'rejected_by', 'rejected_at'
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
