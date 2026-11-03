from .models import AuditEvent


def record_audit(actor, team, action, target):
    """Call within the transaction that applies the related mutation."""
    return AuditEvent.objects.create(
        actor=actor,
        team=team,
        action=action,
        target_type=target._meta.model_name,
        target_id=str(target.pk),
    )
