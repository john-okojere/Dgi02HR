# core/urls.py

from django.contrib import admin
from django.urls import path
from attendance import views

urlpatterns = [
    # Admin (only for superusers)
    path('admin/', admin.site.urls),
    
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Public kiosk
    path('', views.kiosk_view, name='kiosk'),
    
    # Dashboard
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Employee Management
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/add/', views.employee_create, name='employee_create'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/<int:pk>/edit/', views.employee_edit, name='employee_edit'),
    path('employees/<int:pk>/delete/', views.employee_delete, name='employee_delete'),
    
    # Attendance Management
    path('attendance/', views.attendance_reports, name='attendance_reports'),
    path('attendance/add/', views.manual_attendance_add, name='manual_attendance_add'),
    
    # Reports
    path('reports/', views.reports_view, name='reports'),
    path('reports/export/', views.export_attendance_csv, name='export_attendance_csv'),
]