from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import CustomPasswordResetForm

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('recuperar-password/', auth_views.PasswordResetView.as_view(
        template_name='business/password_reset.html',
        form_class=CustomPasswordResetForm,
        email_template_name='business/password_reset_email.txt',
        html_email_template_name='business/password_reset_email.html',
        subject_template_name='business/password_reset_subject.txt'
    ), name='password_reset'),
    path('recuperar-password/enviado/', auth_views.PasswordResetDoneView.as_view(template_name='business/password_reset_done.html'), name='password_reset_done'),
    path('recuperar-password/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='business/password_reset_confirm.html'), name='password_reset_confirm'),
    path('recuperar-password/completo/', auth_views.PasswordResetCompleteView.as_view(template_name='business/password_reset_complete.html'), name='password_reset_complete'),
    path('registro/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('onboarding/', views.onboarding_view, name='onboarding'),
    path('portal-reservas/', views.booking_portal_config_view, name='booking_portal_config'),
    path('portal-reservas/toggle/', views.booking_portal_toggle_api, name='booking_portal_toggle_api'),
    path('config/', views.business_config_view, name='business_config'),
    path('config/empresa/', views.business_config_view),
    path('config/cuenta/', views.user_profile_config_view, name='user_profile_config'),
    path('cambiar-sucursal/', views.switch_branch_view, name='switch_branch'),
    path('equipo/', views.staff_list_view, name='staff_list'),
    path('equipo/crear/', views.staff_create_view, name='staff_create'),
    path('equipo/<uuid:staff_id>/editar/', views.staff_edit_view, name='staff_edit'),
    path('usuarios/', views.user_list_view, name='user_list'),
    path('usuarios/crear/', views.user_create_view, name='user_create'),
    path('usuarios/<uuid:user_id>/editar/', views.user_edit_view, name='user_edit'),
    path('usuarios/<uuid:user_id>/eliminar/', views.user_delete_view, name='user_delete'),
    path('perfiles/', views.role_list_view, name='role_list'),
    path('perfiles/crear/', views.role_create_view, name='role_create'),
    path('perfiles/<uuid:role_id>/editar/', views.role_edit_view, name='role_edit'),
    path('perfiles/<uuid:role_id>/eliminar/', views.role_delete_view, name='role_delete'),
    path('whatsapp-gateway/status/', views.whatsapp_gateway_status_api, name='whatsapp_gateway_status'),
    path('whatsapp-gateway/qr/', views.whatsapp_gateway_qr_api, name='whatsapp_gateway_qr'),
    path('whatsapp-gateway/generate/', views.whatsapp_gateway_generate_api, name='whatsapp_gateway_generate'),
    path('whatsapp-gateway/unlink/', views.whatsapp_gateway_unlink_api, name='whatsapp_gateway_unlink'),
    path('whatsapp-gateway/send-reminder/', views.whatsapp_gateway_send_reminder_api, name='whatsapp_gateway_send_reminder'),
]
