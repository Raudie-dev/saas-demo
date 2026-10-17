from django.urls import path
from . import views

urlpatterns = [
    path('<slug:business_slug>/', views.public_booking_view, name='public_booking'),
    path('<slug:business_slug>/cita/<uuid:appointment_id>/<str:action>/', views.public_appointment_action_view, name='public_appointment_action'),
    path('<slug:business_slug>/api/slots/', views.api_available_slots_view, name='api_available_slots'),
    path('<slug:business_slug>/api/seller-register/', views.api_seller_register_view, name='api_seller_register'),
]
