from django.urls import path
from . import views

urlpatterns = [
    path('', views.ai_dashboard_view, name='ai_dashboard'),
    path('chat/', views.ai_chat_api, name='ai_chat'),
    path('chat/api/', views.ai_chat_api, name='ai_chat_api'),
    path('webhook/whatsapp/', views.whatsapp_webhook_api, name='whatsapp_webhook_api'),
]
