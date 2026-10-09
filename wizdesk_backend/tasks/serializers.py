from rest_framework import serializers
from .models import Task, Subtask
from users.serializers import UserSerializer
import uuid


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

    def validate_priority(self, value):
        valid_priorities = [choice[0] for choice in Subtask.Priority.choices]
        if value not in valid_priorities:
            raise serializers.ValidationError(f"Priority must be one of: {valid_priorities}")
        return value

    def validate_status(self, value):
        valid_statuses = [choice[0] for choice in Subtask.Status.choices]
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Status must be one of: {valid_statuses}")
        return value

    def validate_progress(self, value):
        valid_progress = [choice[0] for choice in Subtask.Progress.choices]
        if value not in valid_progress:
            raise serializers.ValidationError(f"Progress must be one of: {valid_progress}")
        return value

    def validate_assigned_to(self, value):
        if value is not None:
            if not isinstance(value, uuid.UUID):
                try:
                    uuid.UUID(str(value))
                except (ValueError, AttributeError, TypeError):
                    raise serializers.ValidationError("Assigned_to must be a valid UUID.")
        return value


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

    def validate_priority(self, value):
        valid_priorities = [choice[0] for choice in Task.Priority.choices]
        if value not in valid_priorities:
            raise serializers.ValidationError(f"Priority must be one of: {valid_priorities}")
        return value

    def validate_status(self, value):
        valid_statuses = [choice[0] for choice in Task.Status.choices]
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Status must be one of: {valid_statuses}")
        return value


class TaskCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=True)
    description = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=[choice[0] for choice in Task.Priority.choices], default='medium')
    subtasks = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list
    )

    def validate_subtasks(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Subtasks must be a list.")
        
        for i, subtask in enumerate(value):
            if not isinstance(subtask, dict):
                raise serializers.ValidationError(f"Subtask {i} must be an object.")
            if 'title' not in subtask or not subtask['title']:
                raise serializers.ValidationError(f"Subtask {i} must have a title.")
            if 'priority' in subtask:
                valid_priorities = [choice[0] for choice in Subtask.Priority.choices]
                if subtask['priority'] not in valid_priorities:
                    raise serializers.ValidationError(f"Subtask {i} priority must be one of: {valid_priorities}")
            if 'deadline' in subtask and subtask['deadline']:
                # Deadline validation will be handled by the model field
                pass
            if 'assigned_to' in subtask and subtask['assigned_to']:
                try:
                    uuid.UUID(str(subtask['assigned_to']))
                except (ValueError, AttributeError, TypeError):
                    raise serializers.ValidationError(f"Subtask {i} assigned_to must be a valid UUID.")
        return value


class SubtaskUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    deadline = serializers.DateTimeField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=[choice[0] for choice in Subtask.Priority.choices], required=False)
    assigned_to = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=[choice[0] for choice in Subtask.Status.choices], required=False)
    progress = serializers.ChoiceField(choices=[choice[0] for choice in Subtask.Progress.choices], required=False)

    def validate_assigned_to(self, value):
        if value is not None:
            if not isinstance(value, uuid.UUID):
                try:
                    uuid.UUID(str(value))
                except (ValueError, AttributeError, TypeError):
                    raise serializers.ValidationError("Assigned_to must be a valid UUID.")
        return value
