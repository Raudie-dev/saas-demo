from django.urls import path
from . import views

urlpatterns = [
    path('clientes/', views.client_list_view, name='client_list'),
    path('clientes/crear/', views.client_create_view, name='client_create'),
    path('clientes/<uuid:client_id>/', views.client_detail_view, name='client_detail'),
    path('clientes/<uuid:client_id>/editar/', views.client_edit_view, name='client_edit'),
    path('clientes/<uuid:client_id>/eliminar/', views.client_delete_view, name='client_delete'),
    path('proveedores/', views.supplier_list_view, name='supplier_list'),
    path('proveedores/crear/', views.supplier_create_view, name='supplier_create'),
    path('proveedores/<uuid:supplier_id>/editar/', views.supplier_edit_view, name='supplier_edit'),
    path('clientes/exportar/excel/', views.export_clients_excel, name='export_clients_excel'),
    path('clientes/exportar/pdf/', views.export_clients_pdf, name='export_clients_pdf'),
    path('clientes/importar/', views.client_import_view, name='client_import'),
    path('clientes/plantilla/', views.client_template_download_view, name='client_template_download'),
    path('clientes/<uuid:client_id>/anotaciones-servicio/', views.add_client_service_note_view, name='add_client_service_note'),
    path('clientes/<uuid:client_id>/actualizar-notas/', views.update_client_general_notes_view, name='update_client_general_notes'),
    path('anotaciones-servicio/<str:note_id>/eliminar/', views.delete_client_service_note_view, name='delete_client_service_note'),
    path('clientes/<uuid:client_id>/solicitud-inmobiliaria/', views.add_client_property_inquiry_view, name='add_client_property_inquiry'),
    path('solicitudes-inmobiliarias/<uuid:inquiry_id>/estado/', views.update_property_inquiry_status_view, name='update_property_inquiry_status'),
    path('solicitudes-inmobiliarias/<uuid:inquiry_id>/eliminar/', views.delete_property_inquiry_view, name='delete_property_inquiry'),
]
