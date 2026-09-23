from django.urls import path
from . import views

urlpatterns = [
    path('', views.pos_terminal_view, name='pos_terminal'),
    path('caja/', views.cash_register_view, name='cash_register'),
    path('api/quick-client/', views.api_quick_create_client_view, name='pos_quick_client'),
    path('exportar/excel/', views.export_sales_excel, name='export_sales_excel'),
    path('exportar/pdf/', views.export_sales_pdf, name='export_sales_pdf'),
]
