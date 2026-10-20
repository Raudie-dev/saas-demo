from django.urls import path
from . import views

urlpatterns = [
    path('', views.invoice_list_view, name='invoice_list'),
    path('<uuid:invoice_id>/', views.invoice_detail_view, name='invoice_detail'),
    path('gastos/', views.expense_list_view, name='expense_list'),
    path('gastos/crear/', views.expense_create_view, name='expense_create'),
    path('gastos/<uuid:expense_id>/editar/', views.expense_edit_view, name='expense_edit'),
    path('gastos/exportar/excel/', views.export_expenses_excel, name='export_expenses_excel'),
    path('gastos/exportar/pdf/', views.export_expenses_pdf, name='export_expenses_pdf'),

    # Cotizaciones / Presupuestos
    path('cotizaciones/', views.quote_list_view, name='quote_list'),
    path('cotizaciones/crear/', views.quote_create_view, name='quote_create'),
    path('cotizaciones/<uuid:quote_id>/', views.quote_detail_view, name='quote_detail'),
    path('cotizaciones/<uuid:quote_id>/editar/', views.quote_edit_view, name='quote_edit'),
    path('cotizaciones/<uuid:quote_id>/estado/', views.quote_status_update_view, name='quote_status_update'),
    path('cotizaciones/<uuid:quote_id>/convertir-factura/', views.quote_convert_to_invoice_view, name='quote_convert_to_invoice'),
    path('cotizaciones/<uuid:quote_id>/convertir-proyecto/', views.quote_convert_to_project_view, name='quote_convert_to_project'),
    path('cotizaciones/<uuid:quote_id>/eliminar/', views.quote_delete_view, name='quote_delete'),
]

