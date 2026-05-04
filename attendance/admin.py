# attendance/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta
from .models import Category, Department, Employee, AttendanceRecord, AttendanceSettings


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'icon', 'color', 'created_at']
    search_fields = ['name', 'code']
    list_editable = ['icon', 'color']


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at']
    search_fields = ['name', 'code']
    list_filter = ['is_active']
    list_editable = ['is_active']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_id', 'display_name', 'category_badge', 'email', 
                    'department', 'employment_status', 'attendance_status']
    list_filter = ['category', 'department', 'employment_status', 'is_active', 'gender']
    search_fields = ['first_name', 'last_name', 'email', 'employee_id']
    list_editable = ['employment_status']
    readonly_fields = ['employee_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Identification', {
            'fields': ('employee_id', 'category')
        }),
        ('Personal Information', {
            'fields': ('title', 'first_name', 'last_name', 'email', 'personal_email', 
                      'phone', 'gender', 'date_of_birth')
        }),
        ('Work Information', {
            'fields': ('department', 'position', 'hire_date', 'end_date', 'supervisor')
        }),
        ('Intern/Student Information', {
            'fields': ('institution', 'field_of_study', 'student_id'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('employment_status', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def display_name(self, obj):
        return obj.display_name
    display_name.short_description = 'Name'
    display_name.admin_order_field = 'first_name'
    
    def category_badge(self, obj):
        if obj.category:
            return format_html(
                '<span class="badge bg-{}">{}</span>',
                obj.category.color,
                obj.category.name
            )
        return '-'
    category_badge.short_description = 'Category'
    
    def attendance_status(self, obj):
        if obj.is_checked_in_today:
            record = obj.today_attendance
            late = " (Late)" if record and record.is_late else ""
            return format_html(
                '<span style="color: #10b981;">In{}</span>',
                late
            )
        return format_html('<span style="color: #6b7280;">Out</span>')
    attendance_status.short_description = 'Today'


class DateListFilter(admin.SimpleListFilter):
    """Custom filter for filtering by date"""
    title = 'Date'
    parameter_name = 'attendance_date'
    
    def lookups(self, request, model_admin):
        # Get unique dates from the last 30 days
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        dates = AttendanceRecord.objects.filter(
            check_in_time__date__gte=thirty_days_ago
        ).dates('check_in_time', 'day', order='DESC')
        
        return [(d.strftime('%Y-%m-%d'), d.strftime('%Y-%m-%d')) for d in dates[:30]]
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(check_in_time__date=self.value())
        return queryset


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ['employee', 'employee_category', 'date_display', 
                    'check_in_display', 'check_out_display', 'hours_display', 'status_badge']
    list_filter = ['employee__category', DateListFilter]  # Fixed: using custom filter
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__email']
    date_hierarchy = 'check_in_time'  # This gives clickable date drill-down
    
    def employee_category(self, obj):
        if obj.employee.category:
            return format_html(
                '<span class="badge bg-{}">{}</span>',
                obj.employee.category.color,
                obj.employee.category.code
            )
        return '-'
    employee_category.short_description = 'Cat'
    
    def date_display(self, obj):
        return obj.check_in_time.strftime('%Y-%m-%d')
    date_display.short_description = 'Date'
    date_display.admin_order_field = 'check_in_time'
    
    def check_in_display(self, obj):
        time_str = obj.check_in_time.strftime('%H:%M')
        if obj.is_late:
            return format_html('<span style="color: #f59e0b;">{} (Late)</span>', time_str)
        return time_str
    check_in_display.short_description = 'Check In'
    
    def check_out_display(self, obj):
        if obj.check_out_time:
            return obj.check_out_time.strftime('%H:%M')
        return '-'
    check_out_display.short_description = 'Check Out'
    
    def hours_display(self, obj):
        if obj.hours_worked:
            return f"{obj.hours_worked} hrs"
        return '-'
    hours_display.short_description = 'Hours'
    
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #10b981;">Active</span>')
        return format_html('<span style="color: #3b82f6;">Completed</span>')
    status_badge.short_description = 'Status'


@admin.register(AttendanceSettings)
class AttendanceSettingsAdmin(admin.ModelAdmin):
    list_display = ['workday_start', 'late_threshold', 'birthday_reminder_days', 'internship_reminder_days', 'updated_at']

    def has_add_permission(self, request):
        return not AttendanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
