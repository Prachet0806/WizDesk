import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from users.models import Team # Import Team model

class Task(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='tasks')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_tasks')

    status = models.CharField(max_length=50, choices=Status.choices, default=Status.ACTIVE)
    priority = models.CharField(max_length=50, choices=Priority.choices, default=Priority.MEDIUM)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['active', 'completed', 'archived']), name='task_valid_status'),
            models.CheckConstraint(condition=models.Q(priority__in=['low', 'medium', 'high']), name='task_valid_priority'),
        ]

    def __str__(self):
        return self.title

class Subtask(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        ASSIGNED = "assigned", "Assigned"
        TAKEN = "taken", "Taken"
        COMPLETED = "completed", "Completed"

    class Progress(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In Progress"
        TESTING = "testing", "Testing"
        COMPLETED = "completed", "Completed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_subtasks')

    status = models.CharField(max_length=50, choices=Status.choices, default=Status.AVAILABLE)
    progress = models.CharField(max_length=50, choices=Progress.choices, default=Progress.NOT_STARTED)
    priority = models.CharField(max_length=50, choices=Priority.choices, default=Priority.MEDIUM)

    deadline = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['available', 'assigned', 'taken', 'completed']), name='subtask_valid_status'),
            models.CheckConstraint(condition=models.Q(progress__in=['not_started', 'assigned', 'in_progress', 'testing', 'completed']), name='subtask_valid_progress'),
            models.CheckConstraint(condition=models.Q(priority__in=['low', 'medium', 'high']), name='subtask_valid_priority'),
        ]

    def sync_state(self):
        # Every mutation serializes on the parent, including direct model callers.
        from django.db import transaction
        from .services import refresh_parent, set_subtask_state
        with transaction.atomic():
            parent = Task.objects.select_for_update().get(pk=self.task_id)
            set_subtask_state(self)
            self.save()
            refresh_parent(parent)

    def __str__(self):
        return f"{self.title} (Task: {self.task.title})"
