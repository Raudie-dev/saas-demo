from django.urls import path
from . import views

urlpatterns = [
    path('', views.commission_report_view, name='commission_report'),
]
