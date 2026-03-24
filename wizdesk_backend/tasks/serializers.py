from rest_framework import serializers
from .models import Task, Subtask
from users.serializers import UserSerializer

class SubtaskSerializer(serializers.ModelSerializer):
    assigned_to_details = UserSerializer(source='assigned_to', read_only=True)

    class Meta:
        model = Subtask
        fields = [
            'id', 'task', 'title', 'description', 'assigned_to', 
            'assigned_to_details', 'status', 'progress', 'priority', 
            'deadline', 'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class TaskSerializer(serializers.ModelSerializer):
    subtasks = SubtaskSerializer(many=True, read_only=True)
    created_by_details = UserSerializer(source='created_by', read_only=True)

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'team', 'created_by',
            'created_by_details', 'status', 'created_at', 'updated_at',
            'subtasks'
        ]
        read_only_fields = ['id', 'team', 'created_by', 'created_at', 'updated_at']
