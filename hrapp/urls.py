from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('home/', views.home, name='home'),
    path('homeadmin/', views.homeadmin, name='homeadmin'),
    path('homeadmin/historical_data/', views.historical_data, name='historical_data'),
    path('homeadmin/notifications/', views.notifications, name='notifications'),
    path('homeadmin/camera_feeds/', views.camera_feeds, name='camera_feeds'),
    path('self_service/', views.self_service, name='self_service'),
    path('plot/attendance/', views.plot_attendance, name='plot_attendance'),
    path('plot/gender/', views.plot_gender, name='plot_gender'),
    path('plot/age/', views.plot_age, name='plot_age'),
    path('plot/attendanceagain/', views.plot_attendanceagain, name='plot_attendanceagain'),
    path('generate_pdf/', views.generate_pdf, name='generate_pdf'),
    path('generate_csv/', views.generate_csv, name='generate_csv'),
    path('performance_reviews/', views.performance_reviews, name='performance_reviews'),
    path('leave_application/', views.leave_application, name='leave_application'),
    path('send_notification/', views.send_notification, name='send_notification'),
    path('table/', views.table, name='table'),
    path('data/', views.data, name='data'),
    path('homeadmin/add-review/', views.add_performance_review, name='add_performance_review'),

]
