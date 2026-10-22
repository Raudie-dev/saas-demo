from django.urls import path
from . import views

urlpatterns = [
    # Packages / Tours
    path('', views.package_list_view, name='travel_package_list'),
    path('paquetes/nuevo/', views.package_create_view, name='travel_package_create'),
    path('paquetes/<uuid:package_id>/', views.package_detail_view, name='travel_package_detail'),
    path('paquetes/<uuid:package_id>/editar/', views.package_edit_view, name='travel_package_edit'),
    path('paquetes/<uuid:package_id>/eliminar/', views.package_delete_view, name='travel_package_delete'),

    # Bookings / Passenger Expedientes
    path('reservas/', views.booking_list_view, name='travel_booking_list'),
    path('reservas/nueva/', views.booking_create_view, name='travel_booking_create'),
    path('reservas/<uuid:booking_id>/', views.booking_detail_view, name='travel_booking_detail'),
    path('reservas/<uuid:booking_id>/editar/', views.booking_edit_view, name='travel_booking_edit'),
    path('reservas/<uuid:booking_id>/estado/', views.booking_status_update_view, name='travel_booking_status'),
    path('reservas/<uuid:booking_id>/voucher/', views.booking_voucher_view, name='travel_booking_voucher'),
]
