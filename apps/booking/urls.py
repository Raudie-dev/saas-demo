from django.urls import path
from . import views

urlpatterns = [
    path('<slug:business_slug>/', views.public_booking_view, name='public_booking'),
    path('<slug:business_slug>/api/slots/', views.api_available_slots_view, name='api_available_slots'),
]
