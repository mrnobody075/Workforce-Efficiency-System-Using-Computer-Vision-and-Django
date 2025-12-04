import io

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, JsonResponse, FileResponse
from .models import Employee, Attendance, PerformanceReview, LeaveApplication
from django.core.mail import send_mail
import pandas as pd
# --- at the very top of hrapp/views.py ---
import matplotlib
matplotlib.use('Agg')   # MUST be set before importing pyplot
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Employee
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404
from functools import wraps

def employee_only(view_func):
    """Require normal logged-in user (not staff). Staff are redirected to admin home."""
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, "is_staff", False):
            # optional: you can use messages to inform admin
            return redirect('homeadmin')
        return view_func(request, *args, **kwargs)
    return _wrapped
@staff_member_required(login_url='login')
def add_performance_review(request):
    """
    Admin-only view to add a PerformanceReview for an Employee.
    GET -> show form
    POST -> create review and redirect back with success message
    """
    if request.method == 'POST':
        empid = request.POST.get('employeeid')
        performance = request.POST.get('performance', '').strip()
        feedbacks = request.POST.get('feedbacks', '').strip()

        if not empid:
            messages.error(request, "Please select an employee.")
            return redirect('add_performance_review')

        employee = get_object_or_404(Employee, employeeid=empid)

        # create review
        PerformanceReview.objects.create(
            employee=employee,
            performance=performance or None,
            feedbacks=feedbacks or None
        )

        messages.success(request, f"Performance review saved for {employee.name} ({employee.employeeid}).")
        return redirect('add_performance_review')

    # GET: show form
    employees = Employee.objects.order_by('employeeid').all()
    return render(request, 'admin_add_review.html', {'employees': employees})
# ---------- Authentication (simple) ----------
def login_view(request):
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            # redirect to admin or normal home based on permissions
            if user.is_staff:
                return redirect('homeadmin')
            return redirect('home')
        else:
            error = "Invalid credentials. Please try again."
    return render(request, 'login.html', {'error': error})

@staff_member_required(login_url='login')
def homeadmin(request):
    return render(request, 'homeadmin.html')
@employee_only
def home(request):
    return render(request, 'home.html')

# ---------- Data fetch helpers ----------
def fetch_employee_queryset():
    return Employee.objects.all()

def df_from_queryset(qs):
    # convert to dataframe; select relevant fields
    qs_vals = qs.values()
    return pd.DataFrame.from_records(qs_vals)

# ---------- plotting helpers ----------
def fig_to_response(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return HttpResponse(buf.getvalue(), content_type='image/png')

def plot_monthly_attendance_df(df):
    for col in ['JAN','FEB','MAR']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    attendance = df[['JAN','FEB','MAR']].sum()
    fig, ax = plt.subplots(figsize=(8,6))
    attendance.plot(kind='bar', ax=ax)
    ax.set_title('Monthly Attendance Analysis')
    ax.set_xlabel('Month')
    ax.set_ylabel('Total Attendance')
    return fig

def plot_gender_distribution_df(df):
    if 'GENDER' in df.columns:
        df['GENDER'] = df['GENDER'].fillna('UNKNOWN').str.upper()
        gender_distribution = df['GENDER'].value_counts()
        fig, ax = plt.subplots(figsize=(8,6))
        gender_distribution.plot(kind='pie', autopct='%1.1f%%', ax=ax)
        ax.set_ylabel('')
        return fig
    return None

def plot_age_distribution_df(df):
    if 'AGE' in df.columns:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.hist(df['AGE'].dropna(), bins=10, edgecolor='black')
        ax.set_title('Age Distribution Analysis')
        ax.set_xlabel('AGE')
        ax.set_ylabel('Number of Employees')
        return fig
    return None

# ---------- views that render plots ----------
def plot_attendance(request):
    qs = fetch_employee_queryset()
    df = df_from_queryset(qs)
    fig = plot_monthly_attendance_df(df)
    return fig_to_response(fig)

def plot_gender(request):
    qs = fetch_employee_queryset()
    df = df_from_queryset(qs)
    fig = plot_gender_distribution_df(df)
    if fig:
        return fig_to_response(fig)
    return HttpResponse("No gender data available")

def plot_age(request):
    qs = fetch_employee_queryset()
    df = df_from_queryset(qs)
    fig = plot_age_distribution_df(df)
    if fig:
        return fig_to_response(fig)
    return HttpResponse("No age data available")

# ---------- alternate attendance plot (name/time) ----------
def plot_attendanceagain(request):
    # Build DataFrame from Attendance table
    rows = Attendance.objects.select_related('employee').values_list('employee__name', 'time')
    df = pd.DataFrame(list(rows), columns=['Name','Time'])
    if df.empty:
        return HttpResponse("No attendance data")
    fig, ax = plt.subplots(figsize=(10,6))
    df.groupby('Name')['Time'].sum().plot(kind='bar', ax=ax)
    ax.set_title('Attendance Analysis')
    ax.set_xlabel('Name')
    ax.set_ylabel('Time')
    plt.xticks(rotation=45, ha='right')
    return fig_to_response(fig)

# ---------- table & data endpoints ----------
def table(request):
    qs = fetch_employee_queryset()
    employees = list(qs.values())
    return render(request, 'table.html', {'employees': employees})

def data(request):
    qs = fetch_employee_queryset()
    df = df_from_queryset(qs)
    return HttpResponse(df.to_json(orient='records'), content_type='application/json')
@staff_member_required(login_url='login')
# ---------- generate CSV ----------
def generate_csv(request):
    qs = fetch_employee_queryset()
    df = df_from_queryset(qs)
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    csv_buf.seek(0)
    return HttpResponse(csv_buf.getvalue(), content_type='text/csv', headers={
        'Content-Disposition': 'attachment; filename="employee_data.csv"'
    })

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
import io, traceback
from django.http import FileResponse, JsonResponse
@staff_member_required(login_url='login')
def generate_pdf(request):
    try:
        qs = fetch_employee_queryset()
        df = df_from_queryset(qs)

        images = []

        # helper to create a PNG BytesIO from a matplotlib fig
        def fig_to_buf(fig):
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return buf

        # Attendance
        try:
            fig = plot_monthly_attendance_df(df)
            buf = fig_to_buf(fig)
            images.append((buf, "Monthly Attendance Analysis"))
        except Exception as e:
            print("Attendance plot skipped:", e)

        # Gender
        try:
            fig = plot_gender_distribution_df(df)
            if fig:
                buf = fig_to_buf(fig)
                images.append((buf, "Gender Distribution Analysis"))
        except Exception as e:
            print("Gender plot skipped:", e)

        # Age
        try:
            fig = plot_age_distribution_df(df)
            if fig:
                buf = fig_to_buf(fig)
                images.append((buf, "Age Distribution Analysis"))
        except Exception as e:
            print("Age plot skipped:", e)

        # Attendance by name (explicitly build fig here, avoid calling the view)
        try:
            rows = Attendance.objects.select_related('employee').values_list('employee__name', 'time')
            df2 = pd.DataFrame(list(rows), columns=['Name', 'Time'])
            if not df2.empty:
                fig, ax = plt.subplots(figsize=(10,6))
                df2.groupby('Name')['Time'].sum().plot(kind='bar', ax=ax)
                ax.set_title('Attendance Analysis (By Name)')
                ax.set_xlabel('Name')
                ax.set_ylabel('Time')
                plt.xticks(rotation=45, ha='right')
                buf = fig_to_buf(fig)
                images.append((buf, "Attendance Analysis (By Name)"))
        except Exception as e:
            print("Attendance-by-name skipped:", e)

        # Build PDF
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter,
                                leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("Employee Data Visualization", styles['Title']))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Generated report", styles['Normal']))
        story.append(Spacer(1, 18))

        max_width = doc.width  # available width in points

        for img_buf, caption in images:
            # Use ImageReader to get the original image size (w,h)
            try:
                img_buf.seek(0)
                ir = ImageReader(img_buf)
                img_w, img_h = ir.getSize()  # returns width, height (pixels or units)
                # preserve aspect ratio: scale width to max_width in points, compute height
                # treat img_w/img_h as ratio only — set display width to max_width
                display_w = max_width
                display_h = (img_h / float(img_w)) * display_w if img_w else display_w * 0.6
            except Exception:
                # fallback sizing
                display_w = max_width
                display_h = max_width * 0.6
                img_buf.seek(0)

            # Reset buffer pointer and create ReportLab Image with computed size
            img_buf.seek(0)
            rl_image = RLImage(img_buf, width=display_w, height=display_h)
            story.append(rl_image)
            story.append(Spacer(1, 6))
            story.append(Paragraph(caption, styles['Italic']))
            story.append(Spacer(1, 12))

        if not images:
            story.append(Paragraph("No plots available to include in the report.", styles['Normal']))

        doc.build(story)
        pdf_buffer.seek(0)
        return FileResponse(pdf_buffer, as_attachment=True, filename='employee_data.pdf')

    except Exception as e:
        tb = traceback.format_exc()
        print("generate_pdf platypus error:", tb)
        return JsonResponse({'error': str(e), 'trace': tb}, status=500)


# ---------- performance reviews / leave application ----------
@employee_only
def performance_reviews(request):
    # logged-in user identity
    employee_id = request.user.username

    try:
        employee = Employee.objects.get(employeeid=employee_id)
    except Employee.DoesNotExist:
        return HttpResponseForbidden("You are not linked to an employee record.")

    # Fetch reviews belonging ONLY to this employee
    reviews = PerformanceReview.objects.filter(employee=employee)

    return render(request, 'performance_reviews.html', {
        'employee': employee,
        'reviews': reviews
    })
@employee_only
@employee_only
def leave_application(request):
    # Determine the logged-in employee
    emp_id = request.user.username

    try:
        employee = Employee.objects.get(employeeid=emp_id)
    except Employee.DoesNotExist:
        return HttpResponseForbidden("Employee record not found.")

    success = None
    error_message = None

    if request.method == 'POST':
        leave_type = request.POST.get('leave_type')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason')

        try:
            LeaveApplication.objects.create(
                employee=employee,
                leave_type=leave_type,
                start_date=start_date,
                end_date=end_date,
                reason=reason
            )
            success = "Leave application submitted successfully!"
        except Exception as e:
            error_message = f"An error occurred: {e}"

    return render(request, 'leave_application.html', {
        'employee': employee,
        'success_message': success,
        'error_message': error_message,
    })

# ---------- notifications (email) ----------
from django.core.mail import EmailMessage

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.mail import EmailMessage
from django.contrib import messages

@staff_member_required(login_url='login')
def notifications(request):
    # pass a queryset of employees (or list of tuples if you prefer)
    employees = Employee.objects.exclude(email__isnull=True).exclude(email__exact='').order_by('employeeid')
    return render(request, 'notifications.html', {'employees': employees})


@staff_member_required(login_url='login')
def send_notification(request):
    if request.method != 'POST':
        return redirect('notifications')

    # basic server-side validation
    email = request.POST.get('email')
    email_type = request.POST.get('email_type')

    if not email or '@' not in email:
        messages.error(request, "Invalid recipient email.")
        return redirect('notifications')

    if email_type not in ('shift_change', 'custom_message'):
        messages.error(request, "Invalid email type.")
        return redirect('notifications')

    subject = "Notification"
    message_body = ""
    if email_type == 'shift_change':
        shift_number = request.POST.get('shift_number', '').strip()
        shift_time = request.POST.get('shift_time', '').strip()
        if not shift_number or not shift_time:
            messages.error(request, "Shift number and shift time are required for shift notifications.")
            return redirect('notifications')
        subject = f"Shift Change Notification for Shift {shift_number}"
        message_body = f"Dear Employee,\n\nYour shift has been changed to Shift {shift_number} at {shift_time}.\n\n"
    else:
        subject = request.POST.get('custom_subject', '').strip() or "Notification"
        message_body = request.POST.get('custom_message', '').strip()
        if not message_body:
            messages.error(request, "Custom message cannot be empty.")
            return redirect('notifications')

    try:
        EmailMessage(subject, message_body, to=[email]).send()
        messages.success(request, "Notification sent successfully!")
    except Exception as e:
        messages.error(request, f"Failed to send email: {e}")

    return redirect('notifications')

@staff_member_required(login_url='login')
def camera_feeds(request):
    return render(request, 'camera_feeds.html')
# add these near your other imports
from django.shortcuts import render
import pandas as pd

# ---------------------------
# Helper: summary statistics
# ---------------------------
def calculate_summary_statistics_from_df(df: pd.DataFrame):
    total_employees = len(df)
    if 'GENDER' in df.columns:
        # keep case-insensitive grouping and handle missing
        gender_counts = df['GENDER'].fillna('UNKNOWN').str.upper().value_counts().to_dict()
    else:
        gender_counts = {}
    return {
        'total_employees': total_employees,
        'gender_counts': gender_counts
    }

# ---------------------------
# historical_data view
# ---------------------------
def historical_data(request):
    """
    Renders historical_data page showing summary statistics and links to the plots.
    Assumes you have helpers:
      - fetch_employee_queryset() -> QuerySet of Employee
      - df_from_queryset(qs) -> pandas.DataFrame
    If you didn't create those helpers, use Employee.objects.all() + pd.DataFrame.from_records(...)
    """
    try:
        # If you have the fetch_employee_queryset + df_from_queryset helpers:
        try:
            qs = fetch_employee_queryset()
            df = df_from_queryset(qs)
        except NameError:
            # fallback: import model and build dataframe directly
            from .models import Employee
            qs = Employee.objects.all().values()
            df = pd.DataFrame.from_records(qs)

        summary_stats = calculate_summary_statistics_from_df(df)

        # Pass summary and optional sample rows to template
        sample_rows = df.head(10).to_dict(orient='records') if not df.empty else []
        context = {
            'summary_stats': summary_stats,
            'sample_employees': sample_rows,
        }
        return render(request, 'historical_data.html', context)
    except Exception as e:
        # keep error visible while debugging
        return render(request, 'historical_data.html', {'error': str(e)})
@employee_only
def self_service(request):
    # logged-in user identity
    employee_id = request.user.username

    # find the matching employee row
    try:
        employee = Employee.objects.get(employeeid=employee_id)
    except Employee.DoesNotExist:
        return HttpResponseForbidden("You are not linked to an employee record.")

    if request.method == 'POST':
        phone_no = request.POST.get('phone_no')
        address = request.POST.get('address')
        email = request.POST.get('email')
        dob = request.POST.get('dob')

        employee.phone_no = phone_no
        employee.address = address
        employee.email = email
        employee.dob = dob
        employee.save()

        messages.success(request, "Details updated successfully!")
        return redirect('self_service')

    return render(request, 'self_service.html', {'employee': employee})

