from rest_framework import serializers
from .models import Task, Subtask
import uuid


class SubtaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()
    task_title = serializers.CharField(source='task.title', read_only=True)
    task_priority = serializers.CharField(source='task.priority', read_only=True)
    task_id = serializers.UUIDField(read_only=True)
    task_description = serializers.CharField(source='task.description', read_only=True)

    class Meta:
        model = Subtask
        fields = [
            'id', 'task', 'task_id', 'task_title', 'task_description', 'task_priority', 'title', 'description',
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


class StrictText(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Must be a string.")
        return super().to_internal_value(data)


class PriorityField(StrictText):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        # Unknown strings preserve the current/model default priority.
        return value if value in Task.Priority.values else None


class AwareDateTimeField(serializers.DateTimeField):
    def enforce_timezone(self, value):
        from django.utils import timezone
        if timezone.is_naive(value):
            raise serializers.ValidationError("Include a timezone offset or Z in the deadline.")
        return super().enforce_timezone(value)


class SubtaskInputSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    title = StrictText(max_length=255, required=False)
    description = StrictText(max_length=10000, required=False, allow_blank=True, allow_null=True)
    deadline = AwareDateTimeField(required=False, allow_null=True)
    priority = PriorityField(required=False)
    assigned_to = serializers.UUIDField(required=False, allow_null=True)

    def validate_assigned_to(self, value):
        if value is None:
            return None
        from users.models import User
        from users.permissions import eligible
        user = User.objects.filter(pk=value, team=self.context['team'], role=User.Role.MEMBER,
                                   status=User.Status.APPROVED, is_active=True).first()
        if not user or not eligible(user):
            raise serializers.ValidationError("Assignee must be an approved member of your team.")
        return user


class TaskInputSerializer(serializers.Serializer):
    title = StrictText(max_length=255, required=False)
    description = StrictText(max_length=10000, required=False, allow_blank=True, allow_null=True)
    priority = PriorityField(required=False)
    status = serializers.ChoiceField(choices=Task.Status.choices, required=False)
    expected_updated_at = serializers.DateTimeField(required=False)
    subtasks = SubtaskInputSerializer(many=True, required=False, max_length=100)
    deleted_subtask_ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=100)

    def validate(self, attrs):
        if not self.context.get('updating') and not attrs.get('title'):
            raise serializers.ValidationError({'title': 'Task title is required.'})
        if not self.context.get('updating') and (attrs.get('deleted_subtask_ids') or any('id' in s for s in attrs.get('subtasks', []))):
            raise serializers.ValidationError("New tasks cannot reference existing subtasks.")
        for subtask in attrs.get('subtasks', []):
            if not subtask.get('id') and not subtask.get('title'):
                raise serializers.ValidationError({'subtasks': 'New subtasks require a title.'})
        ids = [s['id'] for s in attrs.get('subtasks', []) if s.get('id')]
        deleted = attrs.get('deleted_subtask_ids', [])
        if len(ids) != len(set(ids)) or len(deleted) != len(set(deleted)) or set(ids) & set(deleted):
            raise serializers.ValidationError("Subtask IDs must be unique and cannot be updated and deleted together.")
        return attrs


TaskCreateSerializer = TaskInputSerializer
SubtaskUpdateSerializer = SubtaskInputSerializer
