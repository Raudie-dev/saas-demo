from django.urls import path
from . import views

urlpatterns = [
    path('', views.commission_report_view, name='commission_report'),
    path('exportar/excel/', views.export_commissions_excel, name='export_commissions_excel'),
    path('exportar/pdf/', views.export_commissions_pdf, name='export_commissions_pdf'),
]
