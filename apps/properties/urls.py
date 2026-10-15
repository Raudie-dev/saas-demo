from django.urls import path
from apps.properties import views

urlpatterns = [
    path('', views.property_list_view, name='property_list'),
    path('nueva/', views.property_create_view, name='property_create'),
    path('<uuid:property_id>/', views.property_detail_view, name='property_detail'),
    path('<uuid:property_id>/editar/', views.property_edit_view, name='property_edit'),
    path('<uuid:property_id>/eliminar/', views.property_delete_view, name='property_delete'),
    path('<uuid:property_id>/toggle-status/', views.property_toggle_status_view, name='property_toggle_status'),
]
