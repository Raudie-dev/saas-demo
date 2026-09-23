from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('reportes/', views.reports_view, name='reports'),
    path('exportar/excel/', views.export_analytics_excel, name='export_analytics_excel'),
    path('exportar/pdf/', views.export_analytics_pdf, name='export_analytics_pdf'),
]
