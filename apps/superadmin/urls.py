from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.superadmin_login_view, name='superadmin_login'),
    path('logout/', views.superadmin_logout_view, name='superadmin_logout'),
    path('', views.superadmin_dashboard_view, name='superadmin_dashboard'),
    path('usuarios/', views.users_list_view, name='superadmin_users'),
    path('usuarios/<uuid:business_id>/', views.user_detail_view, name='superadmin_user_detail'),
    path('agencias/', views.users_list_view, name='superadmin_businesses'),
    path('suscripciones/', views.users_list_view, name='superadmin_subscriptions'),
    path('planes/', views.plans_management_view, name='superadmin_plans'),
    path('metodos-pago/', views.payment_methods_management_view, name='superadmin_payment_methods'),
]
