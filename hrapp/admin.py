# hrapp/admin.py
from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.utils.html import format_html_join
from django.urls import reverse
import secrets

from .models import Employee, Attendance, PerformanceReview, LeaveApplication

@admin.action(description="Create user accounts for selected employees")
def create_user_accounts(modeladmin, request, queryset):
    created = []
    skipped = []
    for emp in queryset:
        username = str(emp.employeeid)
        try:
            user = User.objects.get(username=username)
            skipped.append(username)
            continue
        except User.DoesNotExist:
            # create user
            email = emp.email or ''
            pwd = secrets.token_urlsafe(10)  # ~10-12 chars
            user = User.objects.create_user(username=username, email=email)
            user.set_password(pwd)
            user.is_staff = False
            user.is_superuser = False
            user.save()


            try:
                if hasattr(emp, 'user'):
                    emp.user = user
                    emp.save()
                    linked = True
                else:
                    linked = False
            except Exception:
                linked = False

            created.append((username, pwd, linked))


    if created:
        lines = []
        for username, pwd, linked in created:
            lines.append(f"{username} : {pwd} {'(linked)' if linked else ''}")
        messages.success(request, "Created users:\n" + "\n".join(lines))
    if skipped:
        messages.info(request, "Skipped (already existed): " + ", ".join(skipped))
    if not created and not skipped:
        messages.warning(request, "No employees selected.")

@admin.action(description="Reset password for selected employees (generates new password)")
def reset_employee_passwords(modeladmin, request, queryset):
    changed = []
    not_found = []
    for emp in queryset:
        username = str(emp.employeeid)
        try:
            user = User.objects.get(username=username)
            new_pwd = secrets.token_urlsafe(10)
            user.set_password(new_pwd)
            user.save()
            changed.append((username, new_pwd))
        except User.DoesNotExist:
            not_found.append(username)

    if changed:
        messages.success(request, "Passwords reset:\n" + "\n".join(f"{u} : {p}" for u, p in changed))
    if not_found:
        messages.info(request, "No user found for: " + ", ".join(not_found))

class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employeeid', 'name', 'email', 'GENDER', 'AGE')
    search_fields = ('employeeid', 'name', 'email')
    actions = [create_user_accounts, reset_employee_passwords]

admin.site.register(Employee, EmployeeAdmin)
admin.site.register(Attendance)
admin.site.register(PerformanceReview)
admin.site.register(LeaveApplication)
