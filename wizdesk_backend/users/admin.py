from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Team, TeamTransferRequest

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'name', 'role', 'status', 'team', 'email_verified')
    list_filter = ('role', 'status', 'email_verified')
    search_fields = ('email', 'name', 'team__name')
    ordering = ('-date_joined',)
    
    # Custom fields need to be added to fieldsets to be visible/editable in admin
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Info', {'fields': ('name', 'role', 'status', 'team', 'team_name', 'approved_by', 'approved_at', 'rejected_by', 'rejected_at', 'email_verified')}),
    )

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'leader', 'created_at')
    search_fields = ('name', 'code', 'leader__email')

@admin.register(TeamTransferRequest)
class TeamTransferRequestAdmin(admin.ModelAdmin):
    list_display = ('member', 'current_team', 'future_team', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('member__email', 'current_team__name', 'future_team__name')
