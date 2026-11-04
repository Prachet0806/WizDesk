import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0005_auditevent")]

    operations = [
        migrations.AlterField(
            model_name="team",
            name="leader",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="led_teams",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
