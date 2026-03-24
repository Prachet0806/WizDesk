from django.urls import path
from .views import TeamPerformanceView

urlpatterns = [
    path('team/<str:team_code>', TeamPerformanceView.as_view(), name='team-performance'),
]
