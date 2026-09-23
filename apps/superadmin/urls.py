from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.superadmin_login_view, name='superadmin_login'),
    path('logout/', views.superadmin_logout_view, name='superadmin_logout'),
    path('', views.superadmin_dashboard_view, name='superadmin_dashboard'),
    path('agencias/', views.businesses_list_view, name='superadmin_businesses'),
    path('suscripciones/', views.subscriptions_list_view, name='superadmin_subscriptions'),
    path('planes/', views.plans_management_view, name='superadmin_plans'),
]
