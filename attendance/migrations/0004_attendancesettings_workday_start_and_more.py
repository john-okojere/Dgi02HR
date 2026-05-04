from datetime import time

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0003_attendancesettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancesettings',
            name='workday_start',
            field=models.TimeField(default=time(8, 0), help_text='Official workday start time.'),
        ),
        migrations.AlterField(
            model_name='attendancesettings',
            name='late_threshold',
            field=models.TimeField(default=time(8, 30), help_text='Check-ins at or after this time are marked late.'),
        ),
    ]
