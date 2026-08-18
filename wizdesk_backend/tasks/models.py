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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='tasks')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_tasks')
    
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.ACTIVE)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

    def sync_state(self):
        completed = self.progress == self.Progress.COMPLETED
        if completed:
            self.status = self.Status.COMPLETED
            if not self.completed_at:
                self.completed_at = timezone.now()
        else:
            self.completed_at = None
            if self.assigned_to_id:
                self.status = self.Status.ASSIGNED if self.progress in (
                    self.Progress.NOT_STARTED, self.Progress.ASSIGNED
                ) else self.Status.TAKEN
            else:
                self.status = self.Status.AVAILABLE

        all_completed = completed and not self.task.subtasks.exclude(
            pk=self.pk
        ).exclude(progress=self.Progress.COMPLETED).exists()

        parent = self.task
        parent_status = Task.Status.COMPLETED if all_completed else (
            Task.Status.ACTIVE if parent.status == Task.Status.COMPLETED else parent.status
        )
        if parent.status != parent_status:
            parent.status = parent_status
            parent.save(update_fields=['status', 'updated_at'])

        self.save()

    def __str__(self):
        return f"{self.title} (Task: {self.task.title})"
