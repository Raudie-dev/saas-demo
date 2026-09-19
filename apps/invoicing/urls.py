from django.urls import path
from . import views

urlpatterns = [
    path('', views.invoice_list_view, name='invoice_list'),
    path('<uuid:invoice_id>/', views.invoice_detail_view, name='invoice_detail'),
    path('gastos/', views.expense_list_view, name='expense_list'),
    path('gastos/crear/', views.expense_create_view, name='expense_create'),
    path('gastos/<uuid:expense_id>/editar/', views.expense_edit_view, name='expense_edit'),
]
