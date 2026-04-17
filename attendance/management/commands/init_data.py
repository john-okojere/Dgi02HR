# attendance/management/commands/init_data.py

from django.core.management.base import BaseCommand
from attendance.models import Category, Department


class Command(BaseCommand):
    help = 'Initialize default categories and departments'

    def handle(self, *args, **options):
        # Create Categories
        categories = [
            {
                'name': 'Staff',
                'code': 'STAFF',
                'icon': 'bi-person-badge',
                'color': 'primary',
            },
            {
                'name': 'Intern',
                'code': 'INTERN',
                'icon': 'bi-mortarboard',
                'color': 'success',
            },
            {
                'name': 'Student',
                'code': 'STUDENT',
                'icon': 'bi-backpack',
                'color': 'info',
            },
        ]

        for cat_data in categories:
            category, created = Category.objects.get_or_create(
                code=cat_data['code'],
                defaults=cat_data
            )
            if created:
                self.stdout.write(f"Created category: {category.name}")
            else:
                self.stdout.write(f"Category already exists: {category.name}")

        # Create Departments
        departments = [
            {'name': 'Engineering', 'code': 'ENG'},
            {'name': 'Human Resources', 'code': 'HR'},
            {'name': 'Administration', 'code': 'ADMIN'},
            {'name': 'Management', 'code': 'MGT'},
            {'name': 'Technical', 'code': 'TECH'},
        ]

        for dept_data in departments:
            department, created = Department.objects.get_or_create(
                code=dept_data['code'],
                defaults=dept_data
            )
            if created:
                self.stdout.write(f"Created department: {department.name}")
            else:
                self.stdout.write(f"Department already exists: {department.name}")

        self.stdout.write(self.style.SUCCESS('\nInitialization complete!'))
