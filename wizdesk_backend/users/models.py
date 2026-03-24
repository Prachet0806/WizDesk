import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    # leader will be a ForeignKey to User, but User is defined below. We use string reference.
    leader = models.ForeignKey('User', on_delete=models.CASCADE, related_name='led_teams', null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

class User(AbstractUser):
    class Role(models.TextChoices):
        LEADER = "LEADER", "Leader"
        MEMBER = "MEMBER", "Member"
        ADMIN = "ADMIN", "Admin"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # We use email as the primary login field
    email = models.EmailField(unique=True)
    
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name='members')
    team_name = models.CharField(max_length=255, null=True, blank=True) # For leaders who haven't created a team yet
    
    approved_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_users')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='rejected_users')
    rejected_at = models.DateTimeField(null=True, blank=True)
    
    email_verified = models.BooleanField(default=False)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'name'] # username is still required by AbstractUser but we login via email

    def __str__(self):
        return f"{self.name} ({self.email})"
