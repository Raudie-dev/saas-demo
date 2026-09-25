from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('registro/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('onboarding/', views.onboarding_view, name='onboarding'),
    path('config/', views.business_config_view, name='business_config'),
    path('config/empresa/', views.business_config_view),
    path('config/cuenta/', views.user_profile_config_view, name='user_profile_config'),
    path('cambiar-sucursal/', views.switch_branch_view, name='switch_branch'),
    path('equipo/', views.staff_list_view, name='staff_list'),
    path('equipo/crear/', views.staff_create_view, name='staff_create'),
    path('equipo/<uuid:staff_id>/editar/', views.staff_edit_view, name='staff_edit'),
    path('whatsapp-gateway/status/', views.whatsapp_gateway_status_api, name='whatsapp_gateway_status'),
    path('whatsapp-gateway/qr/', views.whatsapp_gateway_qr_api, name='whatsapp_gateway_qr'),
    path('whatsapp-gateway/generate/', views.whatsapp_gateway_generate_api, name='whatsapp_gateway_generate'),
    path('whatsapp-gateway/unlink/', views.whatsapp_gateway_unlink_api, name='whatsapp_gateway_unlink'),
    path('whatsapp-gateway/send-reminder/', views.whatsapp_gateway_send_reminder_api, name='whatsapp_gateway_send_reminder'),
]
