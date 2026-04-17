# attendance/forms.py

from django import forms
from .models import Employee, AttendanceRecord, Category, Department


class EmployeeForm(forms.ModelForm):
    """Form for adding/editing employees with category-specific fields"""
    
    class Meta:
        model = Employee
        fields = [
            'category', 'title', 'first_name', 'last_name', 
            'email', 'personal_email', 'phone', 'gender',
            'date_of_birth', 'department', 'position',
            'hire_date', 'end_date', 'institution', 
            'field_of_study', 'student_id', 'supervisor',
            'employment_status', 'is_active'
        ]
        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-select',
                'id': 'category-select'
            }),
            'title': forms.Select(attrs={'class': 'form-select'}),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Work email (used for kiosk)'
            }),
            'personal_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Personal email (optional)'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone number'
            }),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Software Developer, Intern, Student'
            }),
            'hire_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'placeholder': 'Start date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'placeholder': 'Expected end date (interns/students)'
            }),
            'institution': forms.TextInput(attrs={
                'class': 'form-control intern-student-field',
                'placeholder': 'University/School name'
            }),
            'field_of_study': forms.TextInput(attrs={
                'class': 'form-control intern-student-field',
                'placeholder': 'Course or program'
            }),
            'student_id': forms.TextInput(attrs={
                'class': 'form-control student-field',
                'placeholder': 'School ID number'
            }),
            'supervisor': forms.Select(attrs={
                'class': 'form-select intern-student-field'
            }),
            'employment_status': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter supervisor choices to only Staff
        staff_category = Category.objects.filter(code='STAFF').first()
        if staff_category:
            self.fields['supervisor'].queryset = Employee.objects.filter(
                category=staff_category,
                is_active=True
            )
        else:
            self.fields['supervisor'].queryset = Employee.objects.none()
        
        # Make fields required based on category (handled by JS, but set initial)
        self.fields['department'].required = False
        self.fields['supervisor'].required = False
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower().strip()
            qs = Employee.objects.filter(email=email)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('A person with this email already exists.')
        return email
    
    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')

        # Staff-specific validation (birthday is now optional for all)
        if category and category.code == 'STAFF':
            if not cleaned_data.get('hire_date'):
                self.add_error('hire_date', 'Hire date is required for Staff.')
            if not cleaned_data.get('department'):
                self.add_error('department', 'Department is required for Staff.')

        # Intern-specific validation
        if category and category.code == 'INTERN':
            if not cleaned_data.get('hire_date'):
                self.add_error('hire_date', 'Start date is required for Interns.')
            if not cleaned_data.get('end_date'):
                self.add_error('end_date', 'End date is required for Interns.')
            if not cleaned_data.get('institution'):
                self.add_error('institution', 'Institution is required for Interns.')

        # Student-specific validation
        if category and category.code == 'STUDENT':
            if not cleaned_data.get('hire_date'):
                self.add_error('hire_date', 'Start date is required for Students.')
            if not cleaned_data.get('end_date'):
                self.add_error('end_date', 'End date is required for Students.')
            if not cleaned_data.get('institution'):
                self.add_error('institution', 'Institution is required for Students.')
            if not cleaned_data.get('student_id'):
                self.add_error('student_id', 'Student ID is required.')

        return cleaned_data


class ManualAttendanceForm(forms.Form):
    """Form for HR to manually add attendance records"""
    
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True, employment_status='active'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label="Select Person"
    )
    
    check_in_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control',
            'type': 'datetime-local'
        }),
        help_text="Date and time of check-in"
    )
    
    check_out_time = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control',
            'type': 'datetime-local'
        }),
        help_text="Leave blank if still working"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Group employees by category in dropdown
        self.fields['employee'].queryset = Employee.objects.filter(
            is_active=True, 
            employment_status='active'
        ).select_related('category').order_by('category__name', 'first_name')


class DateFilterForm(forms.Form):
    """Form for filtering attendance by date"""
    
    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        required=False
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'placeholder': 'From'
        }),
        required=False
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'placeholder': 'To'
        }),
        required=False
    )
    
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
        empty_label="All People"
    )