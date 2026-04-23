from datetime import time

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0002_category_department_alter_employee_options_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('late_threshold', models.TimeField(default=time(9, 0), help_text='Check-ins at or after this time are marked late.')),
                ('birthday_reminder_days', models.PositiveSmallIntegerField(default=7)),
                ('internship_reminder_days', models.PositiveSmallIntegerField(default=14)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Attendance Settings',
                'verbose_name_plural': 'Attendance Settings',
            },
        ),
    ]
