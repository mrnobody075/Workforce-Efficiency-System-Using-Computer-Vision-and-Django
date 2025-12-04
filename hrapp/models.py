from django.db import models
from django.contrib.auth.models import User

class Employee(models.Model):
    employeeid = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
    phone_no = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    GENDER = models.CharField(max_length=20, blank=True, null=True)
    AGE = models.IntegerField(blank=True, null=True)
    JAN = models.IntegerField(default=0)
    FEB = models.IntegerField(default=0)
    MAR = models.IntegerField(default=0)
    # add other months/fields as needed

    def __str__(self):
        return f"{self.employeeid} - {self.name}"

class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    time = models.FloatField()  # or DateTimeField if you have timestamps
    date = models.DateField(auto_now_add=True)

class PerformanceReview(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    performance = models.TextField(blank=True, null=True)
    feedbacks = models.TextField(blank=True, null=True)

class LeaveApplication(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    applied_at = models.DateTimeField(auto_now_add=True)
