from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('registro/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('onboarding/', views.onboarding_view, name='onboarding'),
    path('config/', views.business_config_view, name='business_config'),
    path('equipo/', views.staff_list_view, name='staff_list'),
    path('equipo/crear/', views.staff_create_view, name='staff_create'),
    path('equipo/<uuid:staff_id>/editar/', views.staff_edit_view, name='staff_edit'),
]
