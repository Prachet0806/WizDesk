from django.contrib import admin
from .models import Task, Subtask

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'team', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'team')
    search_fields = ('title', 'description')

@admin.register(Subtask)
class SubtaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'task', 'status', 'progress', 'assigned_to')
    list_filter = ('status', 'progress', 'priority')
    search_fields = ('title', 'task__title')
