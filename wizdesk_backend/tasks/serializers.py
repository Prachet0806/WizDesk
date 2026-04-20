from rest_framework import serializers
from .models import Task, Subtask
from users.serializers import UserSerializer

class SubtaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()
    task_title = serializers.CharField(source='task.title', read_only=True)
    task_priority = serializers.CharField(source='task.priority', read_only=True)

    class Meta:
        model = Subtask
        fields = [
            'id', 'task', 'task_title', 'task_priority', 'title', 'description', 
            'assigned_to', 'assigned_to_name', 'status', 'progress', 'priority', 
            'deadline', 'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.name if obj.assigned_to else None

class TaskSerializer(serializers.ModelSerializer):
    subtasks = SubtaskSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'team', 'created_by',
            'created_by_name', 'status', 'priority', 'created_at', 'updated_at',
            'subtasks'
        ]
        read_only_fields = ['id', 'team', 'created_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        return obj.created_by.name if obj.created_by else None
