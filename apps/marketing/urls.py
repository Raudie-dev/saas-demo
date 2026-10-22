from django.urls import path
from . import views

urlpatterns = [
    path('', views.marketing_dashboard_view, name='marketing_dashboard'),
    path('cupones/crear/', views.coupon_create_view, name='coupon_create'),
    path('cupones/<uuid:coupon_id>/editar/', views.coupon_edit_view, name='coupon_edit'),
    path('giftcards/crear/', views.giftcard_create_view, name='giftcard_create'),
    path('fidelizacion/', views.loyalty_program_view, name='loyalty_program_view'),

    # Email Marketing routes
    path('email-marketing/', views.email_marketing_list_view, name='email_marketing_list'),
    path('email-marketing/crear/', views.email_campaign_create_view, name='email_campaign_create'),
    path('email-marketing/<uuid:campaign_id>/editar/', views.email_campaign_edit_view, name='email_campaign_edit'),
    path('email-marketing/<uuid:campaign_id>/enviar/', views.email_campaign_send_view, name='email_campaign_send'),
    path('email-marketing/<uuid:campaign_id>/previa/', views.email_campaign_preview_view, name='email_campaign_preview'),
    path('email-marketing/<uuid:campaign_id>/eliminar/', views.email_campaign_delete_view, name='email_campaign_delete'),
]
