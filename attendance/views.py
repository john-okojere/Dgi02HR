# attendance/views.py - Complete fixed version

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.db.models import Q, Count
from django.http import HttpResponse
from datetime import timedelta, date
import csv

from .models import Employee, AttendanceRecord, Category, Department
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
        today = now.date()
        
        if action == 'check_in':
            if employee.is_checked_in_today:
                record = employee.today_attendance
                messages.warning(
                    request, 
                    f'{employee.first_name}, you are already checked in since {record.check_in_time.strftime("%H:%M")}.'
                )
                return redirect('kiosk')
            
            AttendanceRecord.objects.create(
                employee=employee,
                check_in_time=now
            )
            messages.success(
                request, 
                f'Welcome, {employee.first_name}! You checked in at {now.strftime("%H:%M")}.'
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
                f'Goodbye, {employee.first_name}! You checked out at {now.strftime("%H:%M")}. '
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
    
    # Statistics
    active_employees = Employee.objects.filter(is_active=True).select_related('category', 'department')
    total_employees = active_employees.count()
    
    todays_records = AttendanceRecord.objects.filter(
        check_in_time__date=today
    ).select_related('employee__category', 'employee__department')
    
    present_count = todays_records.values('employee_id').distinct().count()
    checked_in_count = todays_records.filter(check_out_time__isnull=True).count()
    checked_out_count = todays_records.filter(check_out_time__isnull=False).count()
    late_count = todays_records.filter(check_in_time__hour__gte=9).values('employee_id').distinct().count()
    absent_count = max(total_employees - present_count, 0)
    
    # Recent activity
    recent_attendance = todays_records.order_by('-check_in_time')[:5]
    
    # Birthdays this week
    birthdays_this_week = get_birthdays_this_week()

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
        late_in_category = todays_records.filter(
            employee__category=category,
            check_in_time__hour__gte=9,
        ).values('employee_id').distinct().count()
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
        'checked_in_count': checked_in_count,
        'checked_out_count': checked_out_count,
        'late_count': late_count,
        'absent_count': absent_count,
        'recent_attendance': recent_attendance,
        'birthdays_this_week': birthdays_this_week,
        'anniversaries_this_week': anniversaries_this_week,
        'category_stats': category_stats,
        'page_title': 'Dashboard',
    }
    
    return render(request, 'attendance/dashboard.html', context)


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
            Q(department__name__icontains=search_query)
        )
    
    # Department filter
    department_id = request.GET.get('department', '')
    if department_id and department_id.isdigit():
        employees = employees.filter(department_id=int(department_id))
    
    # Status filter
    status = request.GET.get('status', '')
    if status == 'active':
        employees = employees.filter(is_active=True)
    elif status == 'inactive':
        employees = employees.filter(is_active=False)
    
    # Get unique departments for filter dropdown
    departments = Department.objects.filter(is_active=True).order_by('name')
    
    context = {
        'employees': employees,
        'search_query': search_query,
        'departments': departments,
        'selected_department': department_id,
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
    date_form = DateFilterForm(request.GET)
    
    records = AttendanceRecord.objects.select_related('employee').all()
    
    if date_form.is_valid():
        # Single date filter
        if date_form.cleaned_data.get('date'):
            filter_date = date_form.cleaned_data['date']
            records = records.filter(check_in_time__date=filter_date)
        
        # Date range filter
        elif date_form.cleaned_data.get('start_date') and date_form.cleaned_data.get('end_date'):
            start_date = date_form.cleaned_data['start_date']
            end_date = date_form.cleaned_data['end_date']
            records = records.filter(check_in_time__date__range=[start_date, end_date])
        
        # Employee filter
        if date_form.cleaned_data.get('employee'):
            records = records.filter(employee=date_form.cleaned_data['employee'])
    else:
        # Default: today's records
        today = timezone.now().date()
        records = records.filter(check_in_time__date=today)
    
    records = records.order_by('-check_in_time')
    total_hours = sum((record.hours_worked or 0) for record in records)
    
    context = {
        'records': records,
        'date_form': date_form,
        'total_hours': round(total_hours, 2),
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
    month_start = today.replace(day=1)
    
    # Get all active employees
    total_employees = Employee.objects.filter(is_active=True).count()
    
    # Get today's attendance counts
    todays_records = AttendanceRecord.objects.filter(
        check_in_time__date=today
    )
    checked_in_count = todays_records.filter(check_out_time__isnull=True).count()
    checked_out_count = todays_records.filter(check_out_time__isnull=False).count()
    present_count = todays_records.values('employee_id').distinct().count()
    absent_count = max(total_employees - present_count, 0)
    
    # Department summary
    department_summary = []
    dept_counts = Employee.objects.filter(is_active=True).values('department').annotate(count=Count('id'))
    for item in dept_counts:
        if item['department']:
            department_summary.append({
                'department': item['department'],
                'count': item['count']
            })
    
    # Monthly stats - Fixed for SQLite
    monthly_records = AttendanceRecord.objects.filter(
        check_in_time__date__gte=month_start,
        check_out_time__isnull=False
    ).select_related('employee')
    
    # Build monthly stats manually
    monthly_stats_dict = {}
    for record in monthly_records:
        emp_id = record.employee.id
        emp_name = f"{record.employee.first_name} {record.employee.last_name}"
        emp_dept = record.employee.department
        
        if emp_id not in monthly_stats_dict:
            monthly_stats_dict[emp_id] = {
                'name': emp_name,
                'department': emp_dept,
                'days_present': 0,
                'total_hours': 0.0
            }
        
        monthly_stats_dict[emp_id]['days_present'] += 1
        
        # Calculate hours worked for this record
        if record.hours_worked:
            monthly_stats_dict[emp_id]['total_hours'] += record.hours_worked
    
    # Convert to list for template
    monthly_stats = []
    for emp_id, data in monthly_stats_dict.items():
        data['avg_hours'] = round(data['total_hours'] / data['days_present'], 2) if data['days_present'] > 0 else 0
        data['total_hours'] = round(data['total_hours'], 1)
        monthly_stats.append(data)
    
    # Sort by name
    monthly_stats.sort(key=lambda x: x['name'])
    
    # Calculate attendance rate
    attendance_rate = 0
    if total_employees > 0:
        attendance_rate = round(((checked_in_count + checked_out_count) / total_employees) * 100)
    
    context = {
        'today': today,
        'total_employees': total_employees,
        'checked_in_count': checked_in_count,
        'checked_out_count': checked_out_count,
        'absent_count': absent_count,
        'attendance_rate': attendance_rate,
        'department_summary': department_summary,
        'monthly_stats': monthly_stats,
        'page_title': 'Reports & Analytics',
    }
    
    return render(request, 'attendance/reports.html', context)


@login_required
def export_attendance_csv(request):
    """Export attendance data to CSV"""
    
    # Get date range from request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    date = request.GET.get('date')
    
    records = AttendanceRecord.objects.select_related('employee').all()
    
    if date:
        records = records.filter(check_in_time__date=date)
    elif start_date and end_date:
        records = records.filter(check_in_time__date__range=[start_date, end_date])
    else:
        # Default to today
        today = timezone.now().date()
        records = records.filter(check_in_time__date=today)
    
    # Create HTTP response with CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="attendance_export_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Employee', 'Department', 'Check In', 'Check Out', 'Hours Worked'])
    
    for record in records.order_by('-check_in_time'):
        writer.writerow([
            record.check_in_time.strftime('%Y-%m-%d'),
            record.employee.full_name,
            record.employee.department,
            record.check_in_time.strftime('%H:%M'),
            record.check_out_time.strftime('%H:%M') if record.check_out_time else 'Still Working',
            record.hours_worked or '-'
        ])
    
    return response


# ==================== HELPER FUNCTIONS ====================

def get_birthdays_this_week():
    """Get employees with birthdays in the next 7 days"""
    
    today = date.today()
    week_later = today + timedelta(days=7)
    
    birthdays = []
    
    for employee in Employee.objects.filter(is_active=True, date_of_birth__isnull=False):
        bday = employee.date_of_birth
        birthday_this_year = date(today.year, bday.month, bday.day)
        
        # Check if within next 7 days
        if today <= birthday_this_year <= week_later:
            birthdays.append({
                'employee': employee,
                'date': birthday_this_year,
                'days_until': (birthday_this_year - today).days
            })
    
    birthdays.sort(key=lambda x: x['days_until'])
    return birthdays
