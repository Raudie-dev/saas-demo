from django.urls import path
from . import views

urlpatterns = [
    path('', views.inventory_list_view, name='inventory_list'),
    path('crear/', views.product_create_view, name='product_create'),
    path('<uuid:product_id>/editar/', views.product_edit_view, name='product_edit'),
    path('categorias/crear/', views.product_category_create_view, name='product_category_create'),
]
