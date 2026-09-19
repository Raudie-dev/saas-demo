from django.urls import path
from . import views

urlpatterns = [
    path('', views.pos_terminal_view, name='pos_terminal'),
    path('caja/', views.cash_register_view, name='cash_register'),
]
