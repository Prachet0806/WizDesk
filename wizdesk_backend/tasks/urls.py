from django.urls import path
from .views import (
    TaskCreateView,
    TeamTasksView,
    TeamTasksStatusView,
    TaskDetailView,
    UserAssignedSubtasksView,
    TakeSubtaskView,
    UpdateSubtaskProgressView,
    SubtaskDetailView
)

urlpatterns = [
    # Tasks
    path('tasks/', TaskCreateView.as_view(), name='task-create'),
    path('tasks/team/<str:team_code>', TeamTasksView.as_view(), name='team-tasks'),
    path('tasks/team/<str:team_code>/status/<str:status_val>', TeamTasksStatusView.as_view(), name='team-tasks-status'),
    path('tasks/<uuid:task_id>', TaskDetailView.as_view(), name='task-detail'),

    # Subtasks
    path('tasks/user/<uuid:user_id>/subtasks', UserAssignedSubtasksView.as_view(), name='user-subtasks'),
    path('tasks/subtask/<uuid:subtask_id>/take', TakeSubtaskView.as_view(), name='take-subtask'),
    path('tasks/subtask/<uuid:subtask_id>/progress', UpdateSubtaskProgressView.as_view(), name='update-subtask-progress'),
    path('tasks/subtask/<uuid:subtask_id>', SubtaskDetailView.as_view(), name='subtask-detail'),
]
