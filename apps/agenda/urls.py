from django.urls import path
from . import views

urlpatterns = [
    path('', views.agenda_view, name='agenda'),
    path('calendario/', views.appointment_calendar_view, name='appointment_calendar'),
    path('api/events/', views.appointment_events_api, name='appointment_events_api'),
    path('crear/', views.appointment_create_view, name='appointment_create'),
    path('<uuid:appointment_id>/editar/', views.appointment_edit_view, name='appointment_edit'),
    path('servicios/', views.service_list_view, name='service_list'),
    path('servicios/crear/', views.service_create_view, name='service_create'),
    path('servicios/<uuid:service_id>/editar/', views.service_edit_view, name='service_edit'),
    path('categorias/crear/', views.service_category_create_view, name='service_category_create'),
]
