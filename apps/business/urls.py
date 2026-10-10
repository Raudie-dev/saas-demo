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
    path('dismiss-announcement/<int:announcement_id>/', views.dismiss_announcement_view, name='dismiss_announcement'),
]
