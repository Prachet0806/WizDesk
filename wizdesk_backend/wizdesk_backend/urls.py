"""
URL configuration for wizdesk_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework_simplejwt.views import TokenRefreshView
from django.views.generic import TemplateView
from django.views.static import serve
from django.conf import settings

urlpatterns = [
    # Static Frontend Routes (Priority)
    path('', TemplateView.as_view(template_name='index.html'), name='index'),
    path('index.html', TemplateView.as_view(template_name='index.html')),
    
    path('leader-dashboard/', TemplateView.as_view(template_name='leader-dashboard.html'), name='leader_dashboard'),
    path('leader-dashboard.html', TemplateView.as_view(template_name='leader-dashboard.html')),
    
    path('member-dashboard/', TemplateView.as_view(template_name='member-dashboard.html'), name='member_dashboard'),
    path('member-dashboard.html', TemplateView.as_view(template_name='member-dashboard.html')),
    
    path('register-leader/', TemplateView.as_view(template_name='register-leader.html'), name='register_leader'),
    path('register-leader.html', TemplateView.as_view(template_name='register-leader.html')),
    
    path('member-register/', TemplateView.as_view(template_name='member-register.html'), name='member_register'),
    path('member-register.html', TemplateView.as_view(template_name='member-register.html')),
    
    # API Routes
    path('admin/', admin.site.urls),
    path('api/auth/', include('users.urls')),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/', include('tasks.urls')),
    path('api/performance/', include('performance.urls')),

    # Fallback to serving files from frontend directory (for css, js, images)
    re_path(r'^(?P<path>.*)$', serve, {'document_root': settings.STATICFILES_DIRS[0]}),
]
