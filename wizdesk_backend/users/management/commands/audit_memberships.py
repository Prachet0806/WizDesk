from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q
from django.db.models.functions import Lower
from users.models import User, TeamTransferRequest


class Command(BaseCommand):
    help = 'Read-only audit of email identity and membership inconsistencies before deployment.'

    def handle(self, *args, **options):
        groups = User.objects.annotate(normalized=Lower('email')).values('normalized').annotate(total=Count('pk')).filter(total__gt=1)
        for group in groups:
            ids = list(User.objects.filter(email__iexact=group['normalized']).values_list('pk', flat=True))
            self.stdout.write('Duplicate email identity: ' + ', '.join(map(str, ids)))
        invalid_leaders = User.objects.filter(role='LEADER', team__isnull=False).exclude(team__leader=F('pk'))
        for user in invalid_leaders:
            self.stdout.write(f'Leader ownership mismatch: {user.pk}')
        stranded = User.objects.filter(status='APPROVED', team__isnull=True)
        for user in stranded:
            self.stdout.write(f'Approved account without team: {user.pk}')
        transfers = TeamTransferRequest.objects.filter(status__in=['PENDING_CURRENT', 'PENDING_FUTURE']).exclude(
            member__team=F('current_team'), member__status='APPROVED')
        for transfer in transfers:
            self.stdout.write(f'Obsolete pending transfer: {transfer.pk}')
        self.stdout.write('Audit complete. Resolve conflicting identities manually; no records were changed.')
