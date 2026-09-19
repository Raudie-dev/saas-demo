from django.urls import path
from . import views

urlpatterns = [
    path('<slug:business_slug>/', views.public_booking_view, name='public_booking'),
]
