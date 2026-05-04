# attendance/views.py - Complete fixed version

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.db.models import Q, Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.urls import reverse
from datetime import timedelta, date
import csv

from .models import Employee, AttendanceRecord, Category, Department, AttendanceSettings
from .forms import EmployeeForm, ManualAttendanceForm, DateFilterForm


# ==================== AUTHENTICATION VIEWS ====================

def login_view(request):
    """Custom login view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'registration/login.html')


def logout_view(request):
    """Custom logout view"""
    logout(request)
    return redirect('login')


# ==================== PUBLIC VIEWS ====================

def kiosk_view(request):
    """Public kiosk page for check-in/out - no login required"""
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        action = request.POST.get('action')
        
        if not email:
            messages.error(request, 'Please enter your email address.')
            return redirect('kiosk')
        
        try:
            employee = Employee.objects.get(email=email, is_active=True)
        except Employee.DoesNotExist:
            messages.error(request, f'Email "{email}" not found. Please contact HR.')
            return redirect('kiosk')
        
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()
        
        if action == 'check_in':
            if employee.is_checked_in_today:
                record = employee.today_attendance
                record_local_in = timezone.localtime(record.check_in_time) if record else None
                messages.warning(
                    request, 
                    f'{employee.first_name}, you are already checked in since {record_local_in.strftime("%H:%M")}.'
                )
                return redirect('kiosk')
            
            AttendanceRecord.objects.create(
                employee=employee,
                check_in_time=now
            )
            messages.success(
                request, 
                f'Welcome, {employee.first_name}! You checked in at {local_now.strftime("%H:%M")}.'
            )
            
        elif action == 'check_out':
            record = employee.today_attendance
            
            if not record or not record.is_active:
                messages.error(
                    request, 
                    f'{employee.first_name}, you have not checked in today.'
                )
                return redirect('kiosk')
            
            record.check_out_time = now
            record.save()
            
            hours = record.hours_worked
            messages.success(
                request, 
                f'Goodbye, {employee.first_name}! You checked out at {local_now.strftime("%H:%M")}. '
                f'Hours worked: {hours} hrs.'
            )
        
        return redirect('kiosk')
    
    context = {
        'current_time': timezone.now(),
    }
    return render(request, 'attendance/kiosk.html', context)


# ==================== DASHBOARD VIEWS ====================

@login_required
def dashboard_view(request):
    """Main HR Dashboard"""
    
    today = timezone.now().date()
    settings_obj = get_attendance_settings()
    late_threshold = settings_obj.late_threshold
    workday_start = settings_obj.workday_start
    
    # Statistics
    active_employees = Employee.objects.filter(is_active=True).select_related('category', 'department')
    total_employees = active_employees.count()
    
    todays_records = AttendanceRecord.objects.filter(
        check_in_time__date=today
    ).select_related('employee__category', 'employee__department')
    
    present_count = todays_records.values('employee_id').distinct().count()
    checked_in_count = todays_records.filter(check_out_time__isnull=True).count()
    checked_out_count = todays_records.filter(check_out_time__isnull=False).count()
    late_count = count_distinct_late_employees(todays_records)
    absent_count = max(total_employees - present_count, 0)
    
    # Recent activity
    recent_attendance = todays_records.order_by('-check_in_time')[:5]

    # Birthdays this week
    birthdays_this_week = get_upcoming_birthdays()
    internship_endings = get_upcoming_internship_endings()

    # Work anniversaries this week (Staff only)
    anniversaries_this_week = []
    staff_employees = active_employees.filter(category__code='STAFF', hire_date__isnull=False)
    for employee in staff_employees:
        info = employee.get_anniversary_this_week()
        if info:
            anniversaries_this_week.append({
                'employee': employee,
                **info,
            })
    anniversaries_this_week.sort(key=lambda x: x['days_until'])

    # Per-category breakdown
    category_stats = []
    for category in Category.objects.order_by('name'):
        total_in_category = active_employees.filter(category=category).count()
        present_in_category = todays_records.filter(employee__category=category).values('employee_id').distinct().count()
        late_in_category = count_distinct_late_employees(todays_records.filter(employee__category=category))
        category_stats.append({
            'category': category,
            'total': total_in_category,
            'present': present_in_category,
            'late': late_in_category,
            'absent': max(total_in_category - present_in_category, 0),
        })
    
    context = {
        'today': today,
        'total_employees': total_employees,
        'present_count': present_count,
        'checked_in_count': checked_in_count,
        'checked_out_count': checked_out_count,
        'late_count': late_count,
        'absent_count': absent_count,
        'recent_attendance': recent_attendance,
        'birthdays_this_week': birthdays_this_week,
        'internship_endings': internship_endings,
        'anniversaries_this_week': anniversaries_this_week,
        'category_stats': category_stats,
        'kiosk_url': request.build_absolute_uri(reverse('kiosk')),
        'late_threshold': late_threshold,
        'workday_start': workday_start,
        'page_title': 'Dashboard',
    }
    
    return render(request, 'attendance/dashboard.html', context)


@login_required
def category_dashboard(request, code):
    """Dashboard view scoped to a single employee category."""

    today = timezone.now().date()
    category = get_object_or_404(Category, code=code.upper())

    category_employees = Employee.objects.filter(category=category).select_related('department', 'category')
    active_category_employees = category_employees.filter(is_active=True)

    search_query = request.GET.get('search', '').strip()
    department_id = request.GET.get('department', '')
    status = request.GET.get('status', '')

    employees = category_employees
    if search_query:
        employees = employees.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(employee_id__icontains=search_query) |
            Q(department__name__icontains=search_query)
        )

    if department_id and department_id.isdigit():
        employees = employees.filter(department_id=int(department_id))

    if status == 'active':
        employees = employees.filter(is_active=True)
    elif status == 'inactive':
        employees = employees.filter(is_active=False)

    todays_records = AttendanceRecord.objects.filter(
        employee__category=category,
        check_in_time__date=today,
    ).select_related('employee__category', 'employee__department')

    total_employees = active_category_employees.count()
    present_count = todays_records.values('employee_id').distinct().count()
    checked_in_count = todays_records.filter(check_out_time__isnull=True).count()
    checked_out_count = todays_records.filter(check_out_time__isnull=False).count()
    late_count = count_distinct_late_employees(todays_records)
    absent_count = max(total_employees - present_count, 0)
    recent_attendance = todays_records.order_by('-check_in_time')[:8]

    context = {
        'category': category,
        'today': today,
        'total_employees': total_employees,
        'present_count': present_count,
        'checked_in_count': checked_in_count,
        'checked_out_count': checked_out_count,
        'late_count': late_count,
        'absent_count': absent_count,
        'employees': employees.order_by('first_name', 'last_name'),
        'recent_attendance': recent_attendance,
        'departments': Department.objects.filter(is_active=True).order_by('name'),
        'search_query': search_query,
        'selected_department': department_id,
        'selected_status': status,
        'page_title': f'{category.name} Dashboard',
    }

    return render(request, 'attendance/category_dashboard.html', context)


# ==================== EMPLOYEE MANAGEMENT VIEWS ====================

@login_required
def employee_list(request):
    """List all employees with search and filter"""
    
    employees = Employee.objects.select_related('department', 'category').all()
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        employees = employees.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(employee_id__icontains=search_query) |
            Q(department__name__icontains=search_query)
        )
    
    # Department filter
    department_id = request.GET.get('department', '')
    if department_id and department_id.isdigit():
        employees = employees.filter(department_id=int(department_id))

    category_id = request.GET.get('category', '')
    if category_id and category_id.isdigit():
        employees = employees.filter(category_id=int(category_id))
    
    # Status filter
    status = request.GET.get('status', '')
    if status == 'active':
        employees = employees.filter(is_active=True)
    elif status == 'inactive':
        employees = employees.filter(is_active=False)
    
    # Get unique departments for filter dropdown
    departments = Department.objects.filter(is_active=True).order_by('name')
    categories = Category.objects.order_by('name')
    
    context = {
        'employees': employees,
        'search_query': search_query,
        'departments': departments,
        'categories': categories,
        'selected_department': department_id,
        'selected_category': category_id,
        'selected_status': status,
        'page_title': 'Employee Management',
    }
    
    return render(request, 'attendance/employee_list.html', context)


@login_required
def employee_create(request):
    """Add new employee"""
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save()
            messages.success(request, f'{employee.full_name} has been added successfully.')
            return redirect('employee_list')
    else:
        form = EmployeeForm()
    
    context = {
        'form': form,
        'page_title': 'Add Employee',
        'action': 'Add',
    }
    
    return render(request, 'attendance/employee_form.html', context)


@login_required
def employee_edit(request, pk):
    """Edit existing employee"""
    
    employee = get_object_or_404(Employee, pk=pk)
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, f'{employee.full_name} has been updated successfully.')
            return redirect('employee_list')
    else:
        form = EmployeeForm(instance=employee)
    
    context = {
        'form': form,
        'employee': employee,
        'page_title': f'Edit: {employee.full_name}',
        'action': 'Update',
    }
    
    return render(request, 'attendance/employee_form.html', context)


@login_required
def employee_delete(request, pk):
    """Delete employee"""
    
    employee = get_object_or_404(Employee, pk=pk)
    
    if request.method == 'POST':
        name = employee.full_name
        employee.delete()
        messages.success(request, f'{name} has been deleted.')
        return redirect('employee_list')
    
    context = {
        'employee': employee,
        'page_title': f'Delete: {employee.full_name}',
    }
    
    return render(request, 'attendance/employee_confirm_delete.html', context)


@login_required
def employee_detail(request, pk):
    """View employee details with attendance history"""
    
    employee = get_object_or_404(Employee, pk=pk)
    
    # Get attendance history
    attendance_history = AttendanceRecord.objects.filter(
        employee=employee
    ).order_by('-check_in_time')[:30]
    
    context = {
        'employee': employee,
        'attendance_history': attendance_history,
        'page_title': employee.full_name,
    }
    
    return render(request, 'attendance/employee_detail.html', context)


# ==================== ATTENDANCE MANAGEMENT VIEWS ====================

@login_required
def attendance_reports(request):
    """Attendance reports with date filtering"""
    
    # Date filter form
    date_form = DateFilterForm(request.GET or None)
    records = build_filtered_attendance_queryset(date_form, default_to_today=True)
    records = records.order_by('-check_in_time')
    total_hours = sum((record.hours_worked or 0) for record in records)
    late_records = sum(1 for record in records if record.is_late)
    recent_attendance_days = list(
        AttendanceRecord.objects.filter(employee__is_active=True)
        .annotate(attendance_date=TruncDate('check_in_time'))
        .values('attendance_date')
        .annotate(
            people_count=Count('employee_id', distinct=True),
            total_records=Count('id'),
            completed_records=Count('id', filter=Q(check_out_time__isnull=False)),
        )
        .order_by('-attendance_date')[:14]
    )
    
    context = {
        'records': records,
        'date_form': date_form,
        'total_hours': round(total_hours, 2),
        'late_records': late_records,
        'recent_attendance_days': recent_attendance_days,
        'page_title': 'Attendance Reports',
    }
    
    return render(request, 'attendance/attendance_reports.html', context)


@login_required
def manual_attendance_add(request):
    """HR manually adds attendance record"""
    
    if request.method == 'POST':
        form = ManualAttendanceForm(request.POST)
        if form.is_valid():
            employee = form.cleaned_data['employee']
            check_in = form.cleaned_data['check_in_time']
            check_out = form.cleaned_data['check_out_time']
            
            AttendanceRecord.objects.create(
                employee=employee,
                check_in_time=check_in,
                check_out_time=check_out
            )
            
            messages.success(request, f'Attendance recorded for {employee.full_name}')
            return redirect('attendance_reports')
    else:
        form = ManualAttendanceForm()
    
    context = {
        'form': form,
        'page_title': 'Add Attendance Record',
    }
    
    return render(request, 'attendance/manual_attendance_form.html', context)


# ==================== REPORT VIEWS ====================

@login_required
def reports_view(request):
    """Generate and export reports"""
    
    today = timezone.now().date()
    date_form = DateFilterForm(request.GET or None)
    records = build_filtered_attendance_queryset(date_form).order_by('-check_in_time')
    employee_scope = build_employee_scope(date_form.cleaned_data if date_form.is_valid() else {})
    records_total = records.count()

    total_employees = employee_scope.count()
    present_count = records.values('employee_id').distinct().count()
    checked_in_count = records.filter(check_out_time__isnull=True).count()
    checked_out_count = records.filter(check_out_time__isnull=False).count()
    late_records = sum(1 for record in records if record.is_late)
    total_hours = round(sum((record.hours_worked or 0) for record in records), 2)
    avg_daily_hours = round((total_hours / checked_out_count), 2) if checked_out_count else 0
    attendance_rate = round((present_count / total_employees) * 100) if total_employees else 0
    absent_count = max(total_employees - present_count, 0)

    department_summary = build_scope_breakdown(employee_scope, 'department', 'department__name')
    category_summary = build_scope_breakdown(employee_scope, 'category', 'category__name')
    trend_data = build_attendance_trend(records)
    person_hours_summary = build_person_hours_summary(records)
    top_people = person_hours_summary[:6]
    has_completed_hours = any(row['total_hours'] > 0 for row in person_hours_summary)

    context = {
        'today': today,
        'date_form': date_form,
        'records': records[:20],
        'records_total': records_total,
        'total_employees': total_employees,
        'present_count': present_count,
        'checked_in_count': checked_in_count,
        'checked_out_count': checked_out_count,
        'late_records': late_records,
        'total_hours': total_hours,
        'avg_daily_hours': avg_daily_hours,
        'absent_count': absent_count,
        'attendance_rate': attendance_rate,
        'department_summary': department_summary,
        'category_summary': category_summary,
        'trend_data': trend_data,
        'top_people': top_people,
        'has_completed_hours': has_completed_hours,
        'birthdays_this_week': get_upcoming_birthdays(),
        'internship_endings': get_upcoming_internship_endings(),
        'page_title': 'Reports & Analytics',
    }
    
    return render(request, 'attendance/reports.html', context)


@login_required
def export_attendance_csv(request):
    """Export attendance data to CSV"""
    date_form = DateFilterForm(request.GET or None)
    export_scope = request.GET.get('scope')
    records = build_filtered_attendance_queryset(
        date_form,
        default_to_today=(export_scope != 'reports'),
        default_to_current_month=False,
    ).order_by('-check_in_time')
    
    # Create HTTP response with CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="attendance_export_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Employee ID', 'Employee', 'Category', 'Department', 'Employment Status', 'Check In', 'Check Out', 'Hours Worked', 'Attendance Status'])
    
    for record in records:
        writer.writerow([
            record.check_in_time.strftime('%Y-%m-%d'),
            record.employee.employee_id,
            record.employee.full_name,
            record.employee.category.name,
            record.employee.department,
            record.employee.get_employment_status_display(),
            record.check_in_time.strftime('%H:%M'),
            record.check_out_time.strftime('%H:%M') if record.check_out_time else 'Still Working',
            record.hours_worked or '-',
            record.status.title(),
        ])
    
    return response


# ==================== HELPER FUNCTIONS ====================

def get_attendance_settings():
    return AttendanceSettings.get_solo()


def build_employee_scope(cleaned_data=None):
    cleaned_data = cleaned_data or {}
    employees = Employee.objects.select_related('department', 'category').all()

    if cleaned_data.get('employee'):
        employees = employees.filter(pk=cleaned_data['employee'].pk)
    if cleaned_data.get('category'):
        employees = employees.filter(category=cleaned_data['category'])
    if cleaned_data.get('department'):
        employees = employees.filter(department=cleaned_data['department'])
    if cleaned_data.get('employment_status'):
        employees = employees.filter(employment_status=cleaned_data['employment_status'])
    if cleaned_data.get('search'):
        search = cleaned_data['search'].strip()
        employees = employees.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(employee_id__icontains=search)
        )
    return employees


def build_filtered_attendance_queryset(date_form, default_to_today=False, default_to_current_month=False):
    cleaned_data = date_form.cleaned_data if date_form.is_valid() else {}
    records = AttendanceRecord.objects.select_related('employee__department', 'employee__category').all()
    employees = build_employee_scope(cleaned_data)
    records = records.filter(employee__in=employees)

    if cleaned_data.get('date'):
        records = records.filter(check_in_time__date=cleaned_data['date'])
    elif cleaned_data.get('start_date') and cleaned_data.get('end_date'):
        records = records.filter(check_in_time__date__range=[cleaned_data['start_date'], cleaned_data['end_date']])
    elif default_to_current_month:
        today = timezone.now().date()
        records = records.filter(check_in_time__date__gte=today.replace(day=1))
    elif default_to_today:
        records = records.filter(check_in_time__date=timezone.now().date())

    return records


def build_scope_breakdown(employee_scope, relation_name, order_field):
    if relation_name == 'department':
        queryset = employee_scope.exclude(department__isnull=True)
        rows = queryset.values('department__name').annotate(count=Count('id')).order_by(order_field)
        data = [{'label': row['department__name'], 'count': row['count']} for row in rows]
    else:
        rows = employee_scope.values('category__name').annotate(count=Count('id')).order_by(order_field)
        data = [{'label': row['category__name'], 'count': row['count']} for row in rows]

    max_count = max((row['count'] for row in data), default=1)
    for row in data:
        row['percent'] = round((row['count'] / max_count) * 100) if max_count else 0
    return data


def build_attendance_trend(records):
    daily_totals = {}
    for record in records:
        day = timezone.localtime(record.check_in_time).date()
        key = day.isoformat()
        if key not in daily_totals:
            daily_totals[key] = {'date': day, 'label': day.strftime('%b %d'), 'present': set(), 'hours': 0}
        daily_totals[key]['present'].add(record.employee_id)
        daily_totals[key]['hours'] += record.hours_worked or 0

    data = []
    max_present = 1
    for value in daily_totals.values():
        present = len(value['present'])
        max_present = max(max_present, present)
        data.append({
            'date': value['date'],
            'label': value['label'],
            'present': present,
            'hours': round(value['hours'], 1),
        })

    data.sort(key=lambda item: item['date'])
    for item in data:
        item['percent'] = round((item['present'] / max_present) * 100) if max_present else 0
    return data[-10:]


def count_distinct_late_employees(records):
    employee_ids = {record.employee_id for record in records if record.is_late}
    return len(employee_ids)


def build_person_hours_summary(records):
    summary = {}
    for record in records:
        employee = record.employee
        if employee.pk not in summary:
            summary[employee.pk] = {
                'name': employee.display_name,
                'employee_id': employee.employee_id,
                'department': employee.department,
                'attendance_days': set(),
                'completed_sessions': 0,
                'total_hours': 0,
            }
        summary[employee.pk]['attendance_days'].add(timezone.localtime(record.check_in_time).date())
        if record.hours_worked is not None:
            summary[employee.pk]['completed_sessions'] += 1
            summary[employee.pk]['total_hours'] += record.hours_worked

    rows = list(summary.values())
    for row in rows:
        row['days_present'] = len(row.pop('attendance_days'))
        row['total_hours'] = round(row['total_hours'], 1)
        row['avg_hours'] = round((row['total_hours'] / row['completed_sessions']), 2) if row['completed_sessions'] else 0
    rows.sort(key=lambda item: (item['total_hours'], item['days_present']), reverse=True)
    return rows


def get_upcoming_birthdays(days=None):
    """Get employees with birthdays in the configured reminder window."""

    settings_obj = get_attendance_settings()
    reminder_days = days if days is not None else settings_obj.birthday_reminder_days
    today = date.today()
    week_later = today + timedelta(days=reminder_days)

    birthdays = []

    for employee in Employee.objects.filter(is_active=True, date_of_birth__isnull=False):
        bday = employee.date_of_birth
        birthday_this_year = date(today.year, bday.month, bday.day)
        if birthday_this_year < today:
            birthday_this_year = date(today.year + 1, bday.month, bday.day)

        if today <= birthday_this_year <= week_later:
            birthdays.append({
                'employee': employee,
                'date': birthday_this_year,
                'days_until': (birthday_this_year - today).days
            })

    birthdays.sort(key=lambda x: x['days_until'])
    return birthdays


def get_upcoming_internship_endings(days=None):
    """Get active interns whose end date is approaching."""

    settings_obj = get_attendance_settings()
    reminder_days = days if days is not None else settings_obj.internship_reminder_days
    today = date.today()
    reminder_limit = today + timedelta(days=reminder_days)

    upcoming = []
    interns = Employee.objects.filter(
        is_active=True,
        category__code='INTERN',
        end_date__isnull=False,
        end_date__gte=today,
        end_date__lte=reminder_limit,
    ).select_related('department', 'category', 'supervisor')

    for employee in interns:
        upcoming.append({
            'employee': employee,
            'date': employee.end_date,
            'days_until': (employee.end_date - today).days,
        })

    upcoming.sort(key=lambda x: x['days_until'])
    return upcoming
